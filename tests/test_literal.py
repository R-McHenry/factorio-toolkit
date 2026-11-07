import base64
import json
import os
import tempfile
import unittest
import zlib

from fkcore import codec, fkp, literal
from fkcore.catalog import Catalog

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "nauvis")
PLANT = os.path.join(GAME, "plant-w3.json")
BOX = "-34,-39,-17,-23"
SIGNAL_T = {"name": "signal-T", "type": "virtual"}


def decode(bp):
    return json.loads(zlib.decompress(base64.b64decode(bp[1:])))["blueprint"]


class LiteralImportTest(unittest.TestCase):
    def test_the_kickoff_plant(self):
        ents, size, corner = literal.import_entities(PLANT, "reactor", CAT, BOX)
        self.assertEqual(len(literal.read_entities(PLANT)[0]), 28)
        self.assertEqual(len(ents), 21)                  # the 7 chain poles are outside the box
        self.assertEqual((size, corner), ((17, 16), (-34, -39)))
        keys = {e.key: e for e in ents}
        r = keys["reactor/nuclear-reactor0"]
        self.assertEqual((r.x + corner[0], r.y + corner[1]), (-28.5, -30.5))   # world position
        nets = {}
        for e in ents:
            if e.net:
                nets.setdefault(e.net, []).append(e.name)
        # water (pump -> exchanger) and steam (exchanger -> turbines) are separate pipe groups; each
        # inserter is its own one-inserter route
        self.assertEqual(sorted(nets), ["reactor/fluid0", "reactor/fluid1", "reactor/hand0",
                                        "reactor/hand1"])
        self.assertEqual(sorted(len(v) for k, v in nets.items() if "fluid" in k), [4, 5])
        lay = fkp.Layout("factory", "plant", size)
        lay.insts["reactor"] = fkp.Inst("reactor", "Literal", {}, 0, 0, 0, "x")
        for e in ents:
            lay.add(e)
        self.assertEqual(fkp.invariants(lay, CAT), [])

    def test_a_bare_entity_list(self):
        # 1.4.2: the 2005 player's [{name, x, y}] file read as a blueprint string
        d = tempfile.mkdtemp()
        path = os.path.join(d, "rp.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([{"name": "roboport", "x": 2, "y": 2, "direction": 0},
                       {"name": "medium-electric-pole", "x": 4.5, "y": 0.5}], fh)
        rows, wires = literal.read_entities(path)
        self.assertEqual([(r[0], r[1], r[2]) for r in rows],
                         [("roboport", 2.0, 2.0), ("medium-electric-pole", 4.5, 0.5)])
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"blueprint": {}}, fh)
        with self.assertRaisesRegex(literal.LiteralError, "a Literal file is a blueprint string"):
            literal.read_entities(path)

    def test_the_plants_game_settings(self):
        # the file's blueprint, matched to its entity list by name and position
        rows, wires = literal.read_entities(PLANT)
        self.assertEqual([r[0] for r in rows if r[4]],
                         ["requester-chest", "inserter", "nuclear-reactor", "roboport"])
        self.assertEqual(wires, [(12, 1, 13, 1)])          # bp entities 13 and 14, red
        ents = {e.key: e for e in literal.import_entities(PLANT, "reactor", CAT, BOX)[0]}
        req = json.loads(ents["reactor/requester-chest0"].attrs["config"])["request_filters"]
        self.assertEqual([(f["name"], f["count"], f["max_count"]) for f in req["sections"][0]["filters"]],
                         [("uranium-fuel-cell", 20, 50)])
        self.assertTrue(req["trash_not_requested"])
        fuel = ents["reactor/inserter1"].attrs
        self.assertEqual(fuel["net"], "reactor/hand1")
        self.assertEqual(fuel["wire"], "1,nuclear-reactor0,1")
        cond = json.loads(fuel["config"])["control_behavior"]["circuit_condition"]
        self.assertEqual((cond["first_signal"], cond["comparator"], cond["constant"]),
                         (SIGNAL_T, "<", 550))
        self.assertEqual(json.loads(ents["reactor/nuclear-reactor0"].attrs["config"]),
                         {"control_behavior": {"read_temperature": True,
                                               "temperature_signal": SIGNAL_T}})
        self.assertEqual(ents["reactor/inserter0"].attrs, {"net": "reactor/hand0"})

    def test_the_committed_plant_blueprint(self):
        """plant.fkp -> blueprint: the request, both circuit settings and the red wire, renumbered."""
        with open(os.path.join(GAME, "plant.fkp"), encoding="utf-8") as fh:
            text = fh.read()
        lay = fkp.loads(text)
        bp = codec.fkp_to_blueprint(lay, CAT)
        doc = decode(bp)
        ents = {e["tags"]["src"]: e for e in doc["entities"]}
        req = ents["reactor/requester-chest0"]["request_filters"]
        self.assertEqual(req, {"sections": [{"filters": [
            {"comparator": "=", "count": 20, "index": 1, "max_count": 50,
             "name": "uranium-fuel-cell", "quality": "normal"}], "index": 1}],
            "trash_not_requested": True})
        fuel = ents["reactor/inserter1"]
        self.assertEqual(fuel["control_behavior"], {"circuit_condition": {
            "comparator": "<", "constant": 550, "first_signal": SIGNAL_T}, "circuit_enabled": True})
        reactor = ents["reactor/nuclear-reactor0"]
        self.assertEqual(reactor["control_behavior"],
                         {"read_temperature": True, "temperature_signal": SIGNAL_T})
        self.assertNotIn("fkp", fuel["tags"])            # every setting is a game field
        red = [fuel["entity_number"], 1, reactor["entity_number"], 1]
        self.assertEqual(red, [3, 1, 7, 1])               # the file's 13 and 14, renumbered
        self.assertEqual([w for w in doc["wires"] if w[1] != codec.POLE_COPPER], [red])
        # .fkp -> blueprint -> .fkp is byte-identical, with the derived pole wires and without
        self.assertEqual(fkp.dumps(codec.blueprint_to_fkp(bp)), text)
        self.assertEqual(fkp.dumps(codec.blueprint_to_fkp(codec.fkp_to_blueprint(lay))), text)

    def test_signature_follows_the_file(self):
        a = literal.import_entities(PLANT, "reactor", CAT, BOX)
        b = literal.import_entities(PLANT, "reactor", CAT, "-34,-39,-17,-24")   # one row less
        self.assertEqual(literal.signature(a[0], a[1]),
                         literal.signature(*literal.import_entities(PLANT, "reactor", CAT, BOX)[:2]))
        self.assertNotEqual(literal.signature(a[0], a[1]), literal.signature(b[0], b[1]))

    def test_a_blueprint_string_file(self):
        rows = [{"src": None, "name": "transport-belt", "x": 10.5, "y": 4.5, "direction": 4,
                 "attrs": {}},
                {"src": None, "name": "transport-belt", "x": 11.5, "y": 4.5, "direction": 4,
                 "attrs": {}},
                {"src": None, "name": "iron-chest", "x": 12.5, "y": 4.5, "direction": None,
                 "attrs": {}}]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.txt")
            with open(path, "w") as fh:
                fh.write(codec.blueprint(rows))
            ents, size, corner = literal.import_entities(path, "cell", CAT)
        self.assertEqual((size, corner), ((3, 1), (10, 4)))
        self.assertEqual([(e.key, e.net) for e in ents],
                         [("cell/transport-belt0", "cell/belt0"), ("cell/transport-belt1", "cell/belt0"),
                          ("cell/iron-chest0", None)])

    def test_a_capture_in_world_tiles_cuts_into_literals_that_line_up(self):
        # 2.1.31: fk capture world writes world positions, so a box is in world tiles and two
        # Literals cut from one capture sit as the build stood
        from fkcore import capture
        rows = [{"src": None, "name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4,
                 "attrs": {}},
                {"src": None, "name": "assembling-machine-2", "x": 3.5, "y": 1.5,
                 "direction": None, "attrs": {"recipe": "iron-gear-wheel"}}]
        bp = codec.blueprint(rows)
        at = [[1400.5, -380.5, "transport-belt"], [1403.5, -379.5, "assembling-machine-2"]]
        listed = capture.world_list(bp, at)
        self.assertEqual([(e["wx"], e["wy"]) for e in listed], [(1400.5, -380.5), (1403.5, -379.5)])
        self.assertIsNone(capture.world_list(bp, at[:1]))
        self.assertIsNone(capture.world_list(bp, [at[1], at[0]]))     # names out of order
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "demo.json")
            with open(path, "w") as fh:
                json.dump({"bp": bp, "entities": listed}, fh)
            belt, size, corner = literal.import_entities(path, "w", CAT, box="1398,-382,1402,-378")
            asm, _s, corner2 = literal.import_entities(path, "e", CAT, box="1402,-382,1406,-378")
        self.assertEqual(corner, (1398, -382))
        self.assertEqual([(e.name, e.x, e.y, e.dir) for e in belt], [("transport-belt", 2.5, 1.5, 4)])
        self.assertEqual([(e.name, e.attrs.get("recipe")) for e in asm],
                         [("assembling-machine-2", "iron-gear-wheel")])

    def test_a_blueprint_string_keeps_settings_and_wires_inside_the_box(self):
        rows = [{"src": None, "name": "inserter", "x": 0.5, "y": 0.5, "direction": 4,
                 "attrs": {"config": '{"control_behavior":{"circuit_enabled":true}}'}},
                {"src": None, "name": "requester-chest", "x": 1.5, "y": 0.5, "direction": None,
                 "attrs": {"config": '{"request_filters":{"sections":[{"index":1}]}}'}},
                {"src": None, "name": "small-lamp", "x": 9.5, "y": 0.5, "direction": None,
                 "attrs": {}}]
        doc = decode(codec.blueprint(rows))
        doc["wires"] = [[2, 2, 1, 2], [1, 1, 3, 1]]      # a green pair, and red to the far lamp
        bp = "0" + base64.b64encode(zlib.compress(json.dumps({"blueprint": doc}).encode())).decode()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.txt")
            with open(path, "w") as fh:
                fh.write(bp)
            ents, _size, _corner = literal.import_entities(path, "cell", CAT, "0,0,4,1")
        self.assertEqual([(e.key, e.attrs) for e in ents], [
            ("cell/inserter0", {"config": '{"control_behavior":{"circuit_enabled":true}}',
                                "wire": "2,requester-chest0,2", "net": "cell/hand0"}),
            ("cell/requester-chest0", {"config": '{"request_filters":{"sections":[{"index":1}]}}'})])

    def test_the_auto_malls_combinators(self):
        """2.0.71: a selector combinator and an infinity chest are in the catalog, so a Literal
        with them imports (the circuit auto mall's lab copy was refused)."""
        for name, size in (("selector-combinator", (1, 2)), ("infinity-chest", (1, 1))):
            row = CAT.entity(name)
            self.assertEqual((row["tile_width"], row["tile_height"]), size)
        self.assertTrue(CAT.is_electric("selector-combinator"))
        self.assertFalse(CAT.is_electric("infinity-chest"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mall.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([{"name": "selector-combinator", "x": 0.5, "y": 1, "direction": 0,
                            "config": '{"control_behavior":{"operation":"random"}}'},
                           {"name": "infinity-chest", "x": 2.5, "y": 0.5}], fh)
            rows, _wires = literal.read_entities(path)
            self.assertEqual([r[0] for r in rows], ["selector-combinator", "infinity-chest"])
            literal.import_entities(path, "m", CAT)

    def test_errors(self):
        with self.assertRaises(literal.LiteralError):
            literal.import_entities(PLANT, "r", CAT, "0,0,1,1")          # nothing inside
        with self.assertRaises(literal.LiteralError):
            literal.import_entities(PLANT, "r", CAT, "1,2,3")


if __name__ == "__main__":
    unittest.main()
