"""A requester chest asks the robots for its item: the request is in its .fkp line and in the paste.

Found by the V1 rehearsal (2026-10-20): the gear factory's requester asked for nothing, so no plates
came and no gears were made.
"""
import base64
import json
import unittest
import zlib

from fkcore import codec, expand, lang
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
SRC = """
inbox = Chest<requester, item=iron-plate, rate=1.25/s> @(2, 2)
{extra}
gears = AsmRow<n=2, recipe=iron-gear-wheel>           @(6, 2)
box   = Chest<provider>                               @(2, 12)
net plates_in: inbox -> gears
net gear:      gears -> box
"""


def layout(extra=""):
    f = lang.parse(SRC.format(extra=extra), "t.fk")
    lay, _notes = expand.expand_factory(elaborate(f, dict(f.modules), CAT, "t"), CAT)
    return lay


def blueprint_entities(lay):
    text = codec.fkp_to_blueprint(lay, CAT)
    bp = json.loads(zlib.decompress(base64.b64decode(text[1:])))
    return {e["tags"]["src"]: e for e in bp["blueprint"]["entities"]}


def request(entity):
    (section,) = entity["request_filters"]["sections"]
    (f,) = section["filters"]
    return f["name"], f["count"]


class ChestRequestTest(unittest.TestCase):
    def test_a_requester_asks_for_a_minute_of_its_rate(self):
        lay = layout()
        e = lay.entities["inbox/c0"]
        self.assertEqual(e.attrs["item"], "iron-plate")
        self.assertIn("request_filters", e.attrs["config"])
        self.assertEqual(request(blueprint_entities(lay)["inbox/c0"]), ("iron-plate", 75))

    def test_request_sets_the_count(self):
        lay = layout().entities                                     # the default first
        self.assertNotIn("request_filters", lay["box/c0"].attrs.get("config", ""))  # a provider asks nothing
        f = lang.parse(SRC.format(extra="").replace("rate=1.25/s>", "rate=1.25/s, request=40>"), "t.fk")
        lay2, _ = expand.expand_factory(elaborate(f, dict(f.modules), CAT, "t"), CAT)
        self.assertEqual(request(blueprint_entities(lay2)["inbox/c0"]), ("iron-plate", 40))

    def test_an_unbounded_requester_asks_for_100(self):
        f = lang.parse(SRC.format(extra="").replace(", rate=1.25/s>", ">"), "t.fk")
        lay, _ = expand.expand_factory(elaborate(f, dict(f.modules), CAT, "t"), CAT)
        self.assertEqual(request(blueprint_entities(lay)["inbox/c0"]), ("iron-plate", 100))


if __name__ == "__main__":
    unittest.main()
