"""3.0, Literal ports (FRICTION-REVIEW-3.0 U4, reframed): a JSON Literal's ``"ports"`` names a pipe
or belt of the file and the frame edge it meets. The net ends across that edge, the carrier's
group carries the net, and no other net is laid against it: a refinery's three outputs, each a
port, route out without a short."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import connect, expand, lang, literal, route
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate

CAT = Catalog.load()

BELTS = [{"name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4},
         {"name": "transport-belt", "x": 1.5, "y": 0.5, "direction": 4},
         {"name": "transport-belt", "x": 2.5, "y": 0.5, "direction": 4},
         {"name": "small-electric-pole", "x": 1.5, "y": 1.5}]

PIPES = [{"name": "pipe", "x": 0.5, "y": 0.5}, {"name": "pipe", "x": 1.5, "y": 0.5},
         {"name": "pipe", "x": 2.5, "y": 0.5}, {"name": "small-electric-pole", "x": 1.5, "y": 1.5}]

#: an oil refinery and a pipe up from each of its three outputs to the frame's north edge
REFINERY = [{"name": "oil-refinery", "x": 2.5, "y": 4.5, "direction": 0,
             "recipe": "advanced-oil-processing"},
            {"name": "pipe", "x": 0.5, "y": 1.5}, {"name": "pipe", "x": 0.5, "y": 0.5},
            {"name": "pipe", "x": 2.5, "y": 1.5}, {"name": "pipe", "x": 2.5, "y": 0.5},
            {"name": "pipe", "x": 4.5, "y": 1.5}, {"name": "pipe", "x": 4.5, "y": 0.5}]
REFINERY_PORTS = {"heavy": {"carrier": 2, "side": "n"}, "light": {"carrier": 4, "side": "n"},
                  "gas": {"carrier": 6, "side": "n"}}


class LiteralPortsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fklitports-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, data):
        with open(os.path.join(self.dir, "lit.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def build(self, src):
        path = os.path.join(self.dir, "main.fk")
        f = lang.parse(src, path)
        flat = elaborate(f, dict(f.modules), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat),
                              getattr(flat, "_port_edges", None))
        return flat, lay, r, rep

    def test_a_belt_port_starts_across_its_edge(self):
        self.write({"entities": BELTS, "ports": {"out": {"carrier": 2, "side": "e"}}})
        flat, lay, r, rep = self.build(
            'lit = Literal<file="lit.json"> @(6, 4)\ngb = Chest<provider> @(16, 0)\n'
            "net o items iron-plate: lit.out -> gb\n")
        self.assertEqual(flat.nets["o"].drivers, [("lit/transport-belt2", "iron-plate")])
        self.assertEqual(route.jobs(flat, lay, CAT)["o"].starts, [((9, 4), 1)])
        self.assertEqual(r.failed, {})
        self.assertEqual((rep.nets["o"].status, rep.leaks), ("connected", []))
        # the port's belts carry the net
        self.assertEqual({e.net for e in r.layout.entities.values()
                          if e.owner == "lit" and e.name == "transport-belt"}, {"o"})

    def test_a_belt_port_on_a_turned_literal(self):
        self.write({"entities": BELTS, "ports": {"in": {"carrier": 0, "side": "w"}}})
        flat, lay, r, rep = self.build(
            'src = Chest<requester, item=iron-plate, rate=1/s> @(0, 0)\n'
            'lit = Literal<file="lit.json"> @(6, 4, rot 1)\n'
            "net i: src -> lit.in\n")
        (goal, h), = route.jobs(flat, lay, CAT)["i"].goals
        self.assertEqual(h, 2)                     # west turned once is north: the net flows south
        self.assertEqual(r.failed, {})
        self.assertEqual((rep.nets["i"].status, rep.leaks), ("connected", []))

    def test_a_pipe_port(self):
        self.write({"entities": PIPES, "ports": {"gas": {"carrier": 0, "side": "w"}}})
        flat, _lay, r, rep = self.build(
            'gas = InfinityPipe<fluid=petroleum-gas, rate=30/s> @(0, 8)\n'
            'lit = Literal<file="lit.json"> @(8, 2)\n'
            "net g items petroleum-gas: gas -> lit.gas\n")
        self.assertEqual(flat.nets["g"].consumers, [("lit/pipe0", "petroleum-gas")])
        self.assertEqual(r.failed, {})
        self.assertEqual((rep.nets["g"].status, rep.leaks), ("connected", []))
        # the route meets the carrier only across its west edge
        laid = {(int(e.x), int(e.y)) for e in r.layout.entities.values() if e.owner == "~g"}
        self.assertIn((7, 2), laid)
        self.assertFalse(laid & {(8, 1), (9, 1), (10, 1), (8, 3), (10, 3), (11, 2)})

    def test_a_refinery_s_three_outputs_do_not_short(self):
        self.write({"entities": REFINERY, "ports": REFINERY_PORTS})
        flat, _lay, r, rep = self.build("""
ref = Literal<file="lit.json"> @(20, 20)
c1 = Machine<entity=chemical-plant, recipe=heavy-oil-cracking> @(8, 4)
c2 = Machine<entity=chemical-plant, recipe=light-oil-cracking> @(20, 4)
c3 = Machine<entity=chemical-plant, recipe=plastic-bar> @(32, 4)
net heavy items heavy-oil: ref.heavy -> c1
net light items light-oil: ref.light -> c2
net gas items petroleum-gas: ref.gas -> c3
""")
        self.assertEqual({k: v for k, v in r.failed.items() if k in ("heavy", "light", "gas")}, {})
        for net in ("heavy", "light", "gas"):
            self.assertEqual(rep.nets[net].status, "connected", net)
        self.assertEqual(rep.leaks, [])
        # each output's pipes carry its own net: nothing joins two of them
        self.assertEqual({e.net for e in r.layout.entities.values()
                          if e.owner == "ref" and e.name == "pipe"}, {"heavy", "light", "gas"})

    def test_a_wrapper_module_routes_like_any_module(self):
        self.write({"entities": REFINERY, "ports": REFINERY_PORTS})
        flat, _lay, r, rep = self.build("""
module Refinery size 9x9 {
  port heavy_out : out heavy-oil @n0
  port gas_out   : out petroleum-gas @n8
  ref = Literal<file="lit.json"> @(2, 3)
  net h items heavy-oil: ref.heavy -> heavy_out
  net g items petroleum-gas: ref.gas -> gas_out
}
plant = Refinery @(20, 20)
c1 = Machine<entity=chemical-plant, recipe=heavy-oil-cracking> @(8, 4)
c3 = Machine<entity=chemical-plant, recipe=plastic-bar> @(32, 4)
net heavy: plant.heavy_out -> c1
net gas: plant.gas_out -> c3
""")
        self.assertEqual(r.failed, {})
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {n: "connected" for n in rep.nets})
        self.assertEqual(rep.leaks, [])

    def test_bad_ports(self):
        for ports, want in (({"x": {"carrier": 3, "side": "e"}}, "a port's carrier is a pipe"),
                            ({"x": {"carrier": 0, "side": "up"}}, "is not n, e, s or w"),
                            ({"x": {"carrier": 9, "side": "e"}}, "no entity's index"),
                            ({"x-1": {"carrier": 0, "side": "e"}}, "without dashes")):
            self.write({"entities": PIPES, "ports": ports})
            with self.assertRaises(ElabError, msg=str(ports)) as cm:
                path = os.path.join(self.dir, "main.fk")
                f = lang.parse('lit = Literal<file="lit.json"> @(6, 4)\n', path)
                elaborate(f, dict(f.modules), CAT)
            self.assertIn(want, str(cm.exception))

    def test_capture_writes_the_edge_carriers_as_ports(self):
        from fkcore import capture
        rows = [(e["name"], e["x"], e["y"], e.get("direction")) for e in REFINERY]
        self.assertEqual(capture.ports(rows, CAT),
                         {"n1": {"carrier": 2, "side": "n"}, "n2": {"carrier": 4, "side": "n"},
                          "n3": {"carrier": 6, "side": "n"}})
        rows = [(e["name"], e["x"], e["y"], e.get("direction")) for e in BELTS]
        self.assertEqual(capture.ports(rows, CAT),
                         {"w1": {"carrier": 0, "side": "w"}, "e1": {"carrier": 2, "side": "e"}})
        # what capture writes, a Literal reads back: the refinery's ports route as named
        self.write({"entities": REFINERY,
                    "ports": capture.ports([(e["name"], e["x"], e["y"], e.get("direction"))
                                            for e in REFINERY], CAT)})
        _flat, _lay, r, rep = self.build(
            'ref = Literal<file="lit.json"> @(20, 20)\n'
            "c3 = Machine<entity=chemical-plant, recipe=plastic-bar> @(32, 4)\n"
            "net gas items petroleum-gas: ref.n3 -> c3\n")
        self.assertEqual((r.failed, rep.nets["gas"].status, rep.leaks), ({}, "connected", []))

    def test_ports_of_reads_the_file(self):
        self.write({"entities": PIPES, "ports": {"gas": {"carrier": 2, "side": "E"}}})
        path = os.path.join(self.dir, "lit.json")
        ents, _size, _corner = literal.import_entities(path, "lit", CAT)
        self.assertEqual(literal.ports_of(path, ents, CAT), {"gas": ("lit/pipe2", "e")})


if __name__ == "__main__":
    unittest.main()
