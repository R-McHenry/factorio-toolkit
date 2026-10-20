"""1.1, limited production (Rory, 2026-10-20).

A chest's ``limit=`` is its inventory bar in the paste. CLOG, UNLIMITED and SHARED_SINK say where
production is not limited; the rip estimate says what a build takes up and how long the robots
need for it. The 0534 run met all of it: a copper chest first on red science's belt, 4800 plates
in the network, a 1500-plate chest that held 29 robots for minutes, a 1300-entity hand merge.
"""
import base64
import json
import unittest
import zlib

from fkcore import apply, codec, expand, lang
from fkcore.catalog import Catalog
from fkcore.elaborate import ADVICE, elaborate
from fkcore.sense import Verdict

CAT = Catalog.load()

BASE = """
inbox = Chest<requester, item=iron-plate, rate=1.25/s{inbox}> @(2, 2)
gears = AsmRow<n=2, recipe=iron-gear-wheel>                   @(6, 2)
box   = Chest<provider{box}>                                  @(2, 12)
net plates_in: inbox -> gears
net gear:      gears -> box
"""


def flat_of(src):
    f = lang.parse(src, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def advice(src):
    return sorted((c.code, c.where) for c in flat_of(src).checks if c.code in ADVICE)


def entities(src):
    lay, _notes = expand.expand_factory(flat_of(src), CAT)
    text = codec.fkp_to_blueprint(lay, CAT)
    bp = json.loads(zlib.decompress(base64.b64decode(text[1:])))
    return {e["tags"]["src"]: e for e in bp["blueprint"]["entities"]}


class ChestLimitTest(unittest.TestCase):
    def test_limit_is_the_chest_bar(self):
        got = entities(BASE.format(inbox="", box=", limit=4"))
        self.assertEqual(got["box/c0"]["bar"], 4)
        self.assertNotIn("bar", got["inbox/c0"])

    def test_a_requester_keeps_its_request_with_a_limit(self):
        e = entities(BASE.format(inbox=", limit=2", box=", limit=4"))["inbox/c0"]
        self.assertEqual(e["bar"], 2)
        (section,) = e["request_filters"]["sections"]
        self.assertEqual(section["filters"][0]["name"], "iron-plate")

    def test_a_limit_is_a_positive_number_of_slots(self):
        with self.assertRaises(Exception):
            flat_of(BASE.format(inbox="", box=", limit=0"))


class LimitedProductionChecksTest(unittest.TestCase):
    def test_an_unlimited_chest(self):
        self.assertEqual(advice(BASE.format(inbox="", box="")), [("UNLIMITED", "box")])
        self.assertEqual(advice(BASE.format(inbox="", box=", limit=4")), [])

    def test_a_chest_on_a_net_with_machines(self):
        src = BASE.format(inbox="", box=", limit=4").replace(
            "net plates_in: inbox -> gears", "spare = Chest<provider> @(12, 12)\n"
                                             "net plates_in: inbox -> gears, spare")
        self.assertEqual(advice(src), [("SHARED_SINK", "net plates_in"), ("UNLIMITED", "spare")])
        limited = src.replace("spare = Chest<provider>", "spare = Chest<provider, limit=1>")
        self.assertEqual(advice(limited), [])

    def test_a_sushi_net_clogs(self):
        src = BASE.format(inbox="", box=", limit=4") + (
            "cu  = Chest<requester, item=copper-plate, rate=1/s> @(12, 2)\n"
            "mix = Chest<provider, limit=4>                       @(12, 12)\n"
            "net both: inbox, cu -> mix\n")
        self.assertIn(("CLOG", "net both"), advice(src))

    def test_two_nets_into_one_chest_clog(self):
        src = BASE.format(inbox="", box=", limit=4") + (
            "cu  = Chest<requester, item=copper-plate, rate=1/s> @(12, 2)\n"
            "net copper: cu -> box\n")
        self.assertEqual(advice(src), [("CLOG", "box")])


def v(verdict, name, x=0.5, y=0.5):
    return Verdict(verdict, name, x, y)


class Diff:
    def __init__(self, verdicts):
        self.verdicts = verdicts


class RipEstimateTest(unittest.TestCase):
    #: the 0534 run's plate2 chest: 1500 plates, 29 robots, storage 110 tiles away, 2 a trip
    PLATE2 = {"n": 1, "items": 1500, "robots": 29, "dist": 110, "speed": 4.86, "cargo": 2}

    def test_minutes(self):
        self.assertAlmostEqual(apply.rip_minutes(self.PLATE2), 20.4, delta=0.5)
        self.assertEqual(apply.rip_minutes({"n": 0, "items": 0}), 0.0)

    def test_a_small_rip_is_a_line_only(self):
        line, warn = apply.rip_report({"n": 3, "items": 10, "robots": 50, "dist": 20,
                                       "speed": 4.86, "cargo": 2})
        self.assertIn("takes up 3 structures holding 10 items", line)
        self.assertIsNone(warn)

    def test_a_big_rip_warns_and_says_how_to_make_it_faster(self):
        line, warn = apply.rip_report(self.PLATE2)
        self.assertIn("storage 110 tiles away", line)
        self.assertIn("stop what feeds it first", warn)
        self.assertNotIn("fk merge", warn)

    def test_what_the_apply_takes_up(self):
        rep = Diff([v("NOBODY", "transport-belt", 1, 1), v("WRONG", "inserter", 2, 2),
                    v("OK", "assembling-machine-1"), v("MISSING", "transport-belt")])
        self.assertEqual(apply.rip_points(rep), [(1, 1), (2, 2)])

    def test_a_moved_factory_points_to_merge(self):
        rep = Diff([v("NOBODY", "transport-belt")] * 40 + [v("MISSING", "transport-belt")] * 35
                   + [v("GHOST", "transport-belt")] * 10)
        self.assertEqual(apply.moved(rep), 40)
        _line, warn = apply.rip_report({"n": 40, "items": 0, "robots": 50, "dist": 100,
                                        "speed": 4.86, "cargo": 2}, apply.moved(rep))
        self.assertIn("fk merge A,B --into C", warn)


if __name__ == "__main__":
    unittest.main()
