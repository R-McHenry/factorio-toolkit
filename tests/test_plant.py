"""2.0, the worked example of circuits in the source: games/plant builds, through the build offline,
the starter plant the kickoff pastes (plant-w3.json): its 28 entities and its 9 wires (8 copper
between the poles, 1 red for the fuel saver), and the fuel saver's settings as the game has them.
The committed layout (Rory's arrangement) holds the routes, poles and roboport; the circuit comes
from plant.fk: the test takes every circuit setting and wire record out of the .fkp first."""
import base64
import json
import os
import re
import shutil
import tempfile
import unittest
import zlib

from fkcore import apply as applymod, codec, compose, fkp, flow
from fkcore.catalog import Catalog

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "plant")
#: the plant's frame origin in the world (plot -33,-38)
ORIGIN = (-33, -38)


def decode(text):
    return json.loads(zlib.decompress(base64.b64decode(text[1:])))["blueprint"]


def entities(bp, dx=0, dy=0):
    return sorted((e["name"], e["position"]["x"] + dx, e["position"]["y"] + dy,
                   e.get("direction") or 0) for e in bp["entities"])


def wires(bp, dx=0, dy=0):
    at = {e["entity_number"]: (e["name"], e["position"]["x"] + dx, e["position"]["y"] + dy)
          for e in bp["entities"]}
    return sorted(tuple(sorted([(at[a], ca), (at[b], cb)])) for a, ca, b, cb in bp["wires"])


def by_name(bp, name):
    return [e for e in bp["entities"] if e["name"] == name]


class PlantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(GAME, "plant-w3.json"), encoding="utf-8") as fh:
            cls.ref = decode(json.load(fh)["bp"])

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkplant-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        for name in os.listdir(GAME):
            shutil.copy(os.path.join(GAME, name), self.dir)
        path = os.path.join(self.dir, "plant.fkp")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        bare = [re.sub(r" (if|read|signal)=\S+", "", line) for line in text.splitlines()
                if not line.startswith(("wire ", "w "))]
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(bare) + "\n")
        self.bare = "\n".join(bare)

    def build(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        return ctx

    def test_the_committed_layout_carries_no_circuit_before_the_build(self):
        self.assertNotIn("if=", self.bare)
        self.assertNotIn("\nw ", self.bare)

    def test_it_builds_plant_w3_entity_for_entity_and_wire_for_wire(self):
        ctx = self.build()
        self.assertEqual([(s, str(c)) for s, c in ctx.checks], [])
        route_line, = [line for line in ctx.log if "] route " in line]
        self.assertIn("4 kept (4 pinned from the committed .fkp)", route_line)
        lay = fkp.load(os.path.join(self.dir, "plant.fkp"))
        bp = decode(codec.fkp_to_blueprint(lay, CAT))
        self.assertEqual(len(bp["entities"]), 28)
        self.assertEqual(entities(bp, *ORIGIN), entities(self.ref))
        self.assertEqual(len(bp["wires"]), 9)
        self.assertEqual(wires(bp, *ORIGIN), wires(self.ref))
        self.assertEqual(sorted(w[1] for w in bp["wires"]), [1] + [5] * 8)  # 1 red, 8 copper

    def test_the_fuel_saver_is_set_as_the_game_has_it(self):
        self.build()
        bp = decode(codec.fkp_to_blueprint(fkp.load(os.path.join(self.dir, "plant.fkp")), CAT))
        for name in ("nuclear-reactor", "requester-chest"):
            mine, = by_name(bp, name)
            ref, = by_name(self.ref, name)
            field = "control_behavior" if name == "nuclear-reactor" else "request_filters"
            self.assertEqual(mine[field], ref[field], name)
        mine = {e["position"]["y"]: e for e in by_name(bp, "inserter")}
        ref = {e["position"]["y"] + 38: e for e in by_name(self.ref, "inserter")}
        self.assertEqual(mine[6.5]["control_behavior"], ref[6.5]["control_behavior"])
        self.assertNotIn("control_behavior", mine[5.5])         # the spent cells' inserter

    def test_the_paste_puts_it_where_the_kickoff_does(self):
        self.build()
        surface = fkp.load(os.path.join(self.dir, "nauvis.fkp"))
        s = compose.compose(surface, {"plant": fkp.load(os.path.join(self.dir, "plant.fkp"))},
                            CAT)
        bp = decode(applymod.paste_blueprint(applymod.scope_rows(s), s, CAT))
        self.assertEqual(entities(bp), entities(self.ref))
        self.assertEqual(wires(bp), wires(self.ref))

    def test_the_report_says_what_the_circuit_is(self):
        self.build()
        with open(os.path.join(self.dir, "out", "floorplan.txt"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("circuits plant: gated net fuel: 1 carrier if=signal-T<550 on fuel_ctl",
                      text)
        self.assertIn("circuits plant: behave fuel_saver: require 550 > hx.min_temperature: "
                      "holds (550 > 500)", text)
        self.assertIn("full_load: burning 200 s, coasting 450 s, cells 1 per 650 s", text)


if __name__ == "__main__":
    unittest.main()
