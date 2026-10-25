"""A two-entity fixture as a plain JSON entity list (2.0.16).

Every run before this one that needed a robot feeder had to build a blueprint string: an entity
list dropped the settings, so a requester chest in one could not say what it asks for. The 0928
player found that out at 09:45, read ``literal.py`` and ``codec.py`` off the host over ssh, wrote
``helpers/make_robotloader.py`` and generated a blueprint -- for a chest and an inserter. Now the
list sets its entities itself.
"""
import json
import os
import tempfile
import unittest

from fkcore import literal
from fkcore.catalog import Catalog

CAT = Catalog.load()

LIST = [
    {"name": "requester-chest", "x": 1.5, "y": 1.5, "request": {"logistic-robot": 50}},
    {"name": "fast-inserter", "x": 2.5, "y": 1.5, "direction": 12},
]


class LiteralSettingsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fklit-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def _write(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def test_a_bare_list_carries_a_chests_request(self):
        out, size, origin = literal.import_entities(self._write("feed.json", LIST), "feed", CAT)
        chest = [e for e in out if e.name == "requester-chest"][0]
        cfg = json.loads(chest.attrs["config"])
        flt = cfg["request_filters"]["sections"][0]["filters"][0]
        self.assertEqual((flt["name"], flt["count"], flt["comparator"]),
                         ("logistic-robot", 50, "="))
        hand = [e for e in out if e.name == "fast-inserter"][0]
        self.assertEqual(hand.dir, 12)
        self.assertEqual(size, (2, 1))

    def test_a_listed_entity_sets_its_recipe(self):
        data = [{"name": "assembling-machine-1", "x": 1.5, "y": 1.5, "recipe": "iron-gear-wheel"}]
        out, _size, _origin = literal.import_entities(self._write("asm.json", data), "a", CAT)
        self.assertEqual(out[0].attrs["recipe"], "iron-gear-wheel")

    def test_the_game_fields_pass_verbatim(self):
        fields = {"request_filters": {"sections": [{"index": 1, "filters": [
            {"index": 1, "name": "copper-plate", "count": 20, "comparator": ">", "quality": "normal"}]}]}}
        data = [{"name": "requester-chest", "x": 0.5, "y": 0.5, "config": json.dumps(fields)}]
        out, _size, _origin = literal.import_entities(self._write("raw.json", data), "r", CAT)
        self.assertEqual(json.loads(out[0].attrs["config"]), fields)


if __name__ == "__main__":
    unittest.main()
