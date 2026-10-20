import os
import tempfile
import unittest

from fkcore import codec, fkp, literal
from fkcore.catalog import Catalog

CAT = Catalog.load()
PLANT = os.path.join(os.path.dirname(__file__), "..", "games", "nauvis", "plant-w3.json")
BOX = "-34,-39,-17,-23"


class LiteralImportTest(unittest.TestCase):
    def test_the_kickoff_plant(self):
        ents, size, corner = literal.import_entities(PLANT, "reactor", CAT, BOX)
        self.assertEqual(len(literal.read_entities(PLANT)), 28)
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

    def test_errors(self):
        with self.assertRaises(literal.LiteralError):
            literal.import_entities(PLANT, "r", CAT, "0,0,1,1")          # nothing inside
        with self.assertRaises(literal.LiteralError):
            literal.import_entities(PLANT, "r", CAT, "1,2,3")


if __name__ == "__main__":
    unittest.main()
