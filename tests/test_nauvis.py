"""CORE-V1 step 6, on paper: a nauvis surface with main, a standalone plant and a boot factory."""
import base64
import json
import os
import shutil
import tempfile
import unittest
import zlib

from fkcore import codec, compose, connect, cover, fkp, flow
from fkcore.catalog import Catalog
from fkcore.elaborate import ADVICE, elaborate_file

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "nauvis")
SOURCES = ("main.fk", "plant.fk", "boot.fk", "plant-w3.json", "nauvis.surface",
           "nauvis.build.fkb")
CHAIN = """\
fkp 1 surface nauvis
cover bridge power
e bridge/p0 medium-electric-pole -21.5,-21.5
e bridge/p1 medium-electric-pole -16.5,-16.5
e bridge/p2 medium-electric-pole -11.5,-11.5
e bridge/p3 medium-electric-pole -6.5,-6.5
e bridge/p4 medium-electric-pole -1.5,-1.5
e bridge/p5 medium-electric-pole 3.5,3.5
e bridge/p6 medium-electric-pole 5.5,7.5
"""


class NauvisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="fknauvis-")
        for name in SOURCES:
            shutil.copy(os.path.join(GAME, name), cls.dir)
        with open(os.path.join(cls.dir, "nauvis.fkp"), "w", newline="\n") as fh:
            fh.write(CHAIN)                       # the kickoff's pole chain, before any build
        cls.code, cls.ctx = flow.run(os.path.join(cls.dir, "nauvis.build.fkb"), cat=CAT,
                                     echo=lambda _l: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_surface_composes_with_no_check_line(self):
        self.assertEqual(self.code, 0, self.ctx.log)
        self.assertEqual([(s, c) for s, c in self.ctx.checks if c.code not in ADVICE], [])
        s = self.ctx.composed
        self.assertEqual(sorted(s.plots), ["boot", "main", "plant"])
        self.assertEqual(s.problems, [])
        self.assertEqual(s.whose(-29, -31)[1]["key"], "nauvis:plant/reactor/nuclear-reactor0")

    def test_every_factory_is_on_the_grid_with_generation(self):
        s = self.ctx.composed
        nets = cover.networks(list(s.entities.values()), CAT)
        self.assertEqual(len(nets), 1)
        self.assertTrue(nets[0]["sources"])
        added = [k for k in s.entities if k.startswith("nauvis:bridge/p") and int(k[15:]) >= 7]
        self.assertEqual(len(added), 3)          # boot 1, main 2, all in sanctioned space
        for k in added:
            self.assertEqual(s.whose(s.entities[k].x, s.entities[k].y),
                             ("entity", {"key": k, "name": "medium-electric-pole", "net": None,
                                         "plot": None}))

    def test_boot_feeds_its_chest_by_direct_insertion(self):
        lay = self.ctx.layouts["boot"]
        flat = elaborate_file(os.path.join(self.dir, "boot.fk"), CAT)
        rep = connect.connect(lay, CAT, connect.endpoints(flat))
        self.assertEqual({n: r.status for n, r in rep.nets.items()},
                         {"fuel": "connected", "ore": "connected", "plates": "connected"})
        self.assertEqual([e.name for k, e in lay.entities.items() if k.startswith("~plates/i")],
                         ["fast-inserter"])

    def test_the_committed_plant_is_what_the_flow_writes(self):
        with open(os.path.join(self.dir, "plant.fkp"), encoding="utf-8") as fh, \
                open(os.path.join(GAME, "plant.fkp"), encoding="utf-8") as committed:
            self.assertEqual(fh.read(), committed.read())

    def test_the_surface_blueprint_wires_the_fuel_inserter_to_the_reactor(self):
        # what an apply pastes: the composed rows, the derived pole wires, the plant's red wire
        rows = self.ctx.composed.rows()
        bp = codec.blueprint(rows, wires=codec.pole_wires(rows, CAT))
        doc = json.loads(zlib.decompress(base64.b64decode(bp[1:])))["blueprint"]
        num = {e["tags"]["src"]: e["entity_number"] for e in doc["entities"]}
        self.assertEqual([w for w in doc["wires"] if w[1] != codec.POLE_COPPER],
                         [[num["nauvis:plant/reactor/inserter1"], 1,
                           num["nauvis:plant/reactor/nuclear-reactor0"], 1]])
        chest = doc["entities"][num["nauvis:plant/reactor/requester-chest0"] - 1]
        self.assertEqual(chest["request_filters"]["sections"][0]["filters"][0]["name"],
                         "uranium-fuel-cell")

    def test_written_files_and_a_second_build(self):
        files = {n: open(os.path.join(self.dir, n), encoding="utf-8").read()
                 for n in ("main.fkp", "plant.fkp", "boot.fkp", "nauvis.fkp")}
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0)
        for name, text in files.items():
            with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), text, name)
        with open(os.path.join(self.dir, "out", "floorplan.txt"), encoding="utf-8") as fh:
            self.assertIn("bridge power: every network is already joined", fh.read())


class BridgeUnderAPlotTest(unittest.TestCase):
    """1.2 (the 0534 run): a new plot over the old pole bridge stopped the build with INVARIANT
    shared infrastructure, and the bridge stayed. Now the plot takes the bridge's poles and
    ``floorplan --bridge-power`` lays the bridge again around the plots."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkbridge-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        for name in SOURCES:
            shutil.copy(os.path.join(GAME, name), self.dir)
        with open(os.path.join(self.dir, "nauvis.fkp"), "w", newline="\n") as fh:
            fh.write(CHAIN)
        self.script = os.path.join(self.dir, "nauvis.build.fkb")

    def test_a_plot_over_the_bridge_reroutes_it(self):
        code, ctx = flow.run(self.script, cat=CAT, echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        # an empty plot over bridge/p2 (-11.5,-11.5), the chain from the plant to the rest
        with open(os.path.join(self.dir, "pad.fk"), "w", newline="\n") as fh:
            fh.write("# an empty plot\n")
        with open(os.path.join(self.dir, "nauvis.surface"), "a", newline="\n") as fh:
            fh.write("place pad = pad plot -14,-14 6x6\n")
        code, ctx = flow.run(self.script, cat=CAT, echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        self.assertEqual([c for _s, c in ctx.checks if c.code == "INVARIANT"], [])
        s = ctx.composed
        self.assertEqual(s.problems, [])
        self.assertNotIn("nauvis:bridge/p2", s.entities)
        nets = cover.networks(list(s.entities.values()), CAT)
        self.assertEqual(len(nets), 1)                     # one grid, the plant's generation on it
        self.assertTrue(nets[0]["sources"])
        for k, e in s.entities.items():
            if k.startswith("nauvis:bridge/"):
                self.assertEqual(s.whose(e.x, e.y)[1]["plot"], None, k)
        with open(os.path.join(self.dir, "out", "floorplan.txt"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("bridge power: 1 of its poles stand in a plot now (bridge/p2): taken out, "
                      "the bridge is laid again around the plots", text)
        self.assertIn("bridge power: bridged the network of", text)
        surface = fkp.load(os.path.join(self.dir, "nauvis.fkp"))
        self.assertNotIn("bridge/p2", surface.entities)


if __name__ == "__main__":
    unittest.main()
