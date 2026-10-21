"""1.1 (Rory, 2026-10-20): limited production, rips, stale belts, and the 0534 player's patches.

A chest's ``limit=`` is its inventory bar in the paste. CLOG, UNLIMITED and SHARED_SINK say where
production is not limited, and only there: a mixed belt that requester chests feed, or a mixed
chest with a limit, is fine (the 0534 player's one-off crafters were). The rip estimate says what a
build takes up and how long the robots need; ``fk fresh`` takes up belts with stale items. The
player's own patches (``inserter=``, ``item="a,b"``, a third lab belt, plain direct insertion) are
features now.
"""
import base64
import json
import os
import sys
import unittest
import zlib

from fkcore import apply, codec, expand, fresh, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import ADVICE, elaborate
from fkcore.sense import Verdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kickoff"))
import upgrade_run  # noqa: E402

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


def layout(src):
    lay, _notes = expand.expand_factory(flat_of(src), CAT)
    return lay


def entities(src):
    text = codec.fkp_to_blueprint(layout(src), CAT)
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

    def test_trash_sends_back_what_a_requester_no_longer_asks_for(self):
        # 1.4.2: the 2005 player's stone requester kept 101 copper plates from its old list
        got = entities(BASE.format(inbox=", trash", box=", limit=4"))
        self.assertIs(got["inbox/c0"]["request_filters"]["trash_not_requested"], True)
        plain = entities(BASE.format(inbox="", box=", limit=4"))
        self.assertNotIn("trash_not_requested", plain["inbox/c0"]["request_filters"])

    def test_a_limit_is_a_positive_number_of_slots(self):
        with self.assertRaises(Exception):
            flat_of(BASE.format(inbox="", box=", limit=0"))

    def test_a_requester_asks_for_several_items(self):
        src = BASE.format(inbox="", box=", limit=4").replace(
            "item=iron-plate,", 'item="iron-plate,copper-plate",')
        (section,) = entities(src)["inbox/c0"]["request_filters"]["sections"]
        self.assertEqual([(f["index"], f["name"]) for f in section["filters"]],
                         [(1, "iron-plate"), (2, "copper-plate")])


class LimitedProductionChecksTest(unittest.TestCase):
    def test_unlimited_chests_are_one_line(self):
        self.assertEqual(advice(BASE.format(inbox="", box="")), [("UNLIMITED", "box")])
        self.assertEqual(advice(BASE.format(inbox="", box=", limit=4")), [])
        two = BASE.format(inbox="", box="") + "more = Chest<provider> @(12, 12)\nnet m: gears -> more\n"
        self.assertIn(("UNLIMITED", "box, more"), advice(two))

    def test_a_chest_on_a_net_with_machines(self):
        src = BASE.format(inbox="", box=", limit=4").replace(
            "net plates_in: inbox -> gears", "spare = Chest<provider> @(12, 12)\n"
                                             "net plates_in: inbox -> gears, spare")
        self.assertEqual(advice(src), [("SHARED_SINK", "net plates_in"), ("UNLIMITED", "spare")])
        limited = src.replace("spare = Chest<provider>", "spare = Chest<provider, limit=1>")
        self.assertEqual(advice(limited), [])

    def test_a_mixed_belt_that_machines_feed_can_clog(self):
        src = BASE.format(inbox="", box=", limit=4").replace(
            "net plates_in: inbox -> gears", "pipes = AsmRow<n=1, recipe=pipe> @(6, 20)\n"
                                             "net plates_in: inbox -> gears, pipes").replace(
            "net gear:      gears -> box", "net out: gears, pipes -> box")
        self.assertEqual(advice(src), [("CLOG", "net out")])

    def test_a_mixed_belt_a_requester_feeds_is_limited(self):
        src = ('kit = Chest<requester, item="iron-plate,copper-plate", rate=1/s> @(2, 2)\n'
               "mix = Chest<provider, limit=4>                                    @(2, 12)\n"
               "net both: kit -> mix\n")
        self.assertEqual(advice(src), [])

    def test_two_nets_into_one_unlimited_chest_clog(self):
        cu = ("cu  = Chest<requester, item=copper-plate, rate=1/s> @(12, 2)\n"
              "net copper: cu -> box\n")
        self.assertEqual(advice(BASE.format(inbox="", box="") + cu), [("CLOG", "box")])
        self.assertEqual(advice(BASE.format(inbox="", box=", limit=4") + cu), [])


class PlayerPatchesTest(unittest.TestCase):
    def test_inserter_on_a_row(self):
        src = BASE.format(inbox="", box=", limit=4").replace(
            "AsmRow<n=2, recipe=iron-gear-wheel>", "AsmRow<n=2, recipe=iron-gear-wheel, inserter=inserter>")
        names = {e.name for k, e in layout(src).entities.items() if k.startswith("gears/")}
        self.assertIn("inserter", names)
        self.assertNotIn("fast-inserter", names)

    def test_a_third_lab_belt(self):
        src = ("r = Chest<requester, item=automation-science-pack, rate=0.1/s> @(2, 2)\n"
               "g = Chest<requester, item=logistic-science-pack, rate=0.1/s>   @(2, 12)\n"
               "b = Chest<requester, item=chemical-science-pack, rate=0.1/s>   @(2, 22)\n"
               "labs = LabRow<n=2>                                            @(8, 2)\n"
               "net red: r -> labs\nnet green: g -> labs\nnet blue: b -> labs\n")
        names = [e.name for k, e in layout(src).entities.items() if k.startswith("labs/t")]
        self.assertEqual(names, ["long-handed-inserter"] * 2)

    def test_direct_insertion_by_another_hand(self):
        flat = flat_of("inbox = Chest<requester, item=iron-plate> @(2, 2)\n"
                       "gear  = Assembler<recipe=iron-gear-wheel> @(4, 1)\n"
                       "net plates: inbox -> gear\n")
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT, hand="inserter")
        self.assertEqual([e.name for k, e in r.layout.entities.items() if k.startswith("~plates/")],
                         ["inserter"])
        self.assertEqual(route._HANDS[0], ("fast-inserter",))      # the default is back after it
        with self.assertRaises(ValueError):
            route.route_layout(flat, lay, CAT, hand="long-handed-inserter")

    def test_the_upgrade_keeps_plain_hands(self):
        script = "place           --keep pinned\nroute           --only stale --effort normal\n"
        self.assertIn("route           --only stale --effort normal --hand inserter\n",
                      upgrade_run._hand(script))
        self.assertIsNone(upgrade_run._hand(script.replace("normal", "normal --hand inserter")))


def v(verdict, name, x=0.5, y=0.5, wrong=()):
    return Verdict(verdict, name, x, y, wrong_items=list(wrong))


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


class FakeLink:
    def __init__(self, hands="[]", ordered="2"):
        self.sent, self.hands, self.ordered = [], hands, ordered

    def lua(self, text):
        if "held_stack" in text:                    # the stuck-hands read
            return self.hands
        self.sent.append(text)
        return self.ordered


class FreshTest(unittest.TestCase):
    def fresh(self, r):
        class Look:
            rep = Diff([v("OK", "transport-belt", 1.5, 1.5, ["pipe"]),
                        v("OK", "transport-belt", 2.5, 1.5),
                        v("OK", "underground-belt", 3.5, 1.5, ["steel-plate", "pipe"])])
        saved = fresh.look.run
        fresh.look.run = lambda *a, **k: Look
        game = os.path.join(os.path.dirname(__file__), "..", "kickoff", "template", "game")
        try:
            return fresh.run(r, game, CAT, (0, 0, 10, 10))
        finally:
            fresh.look.run = saved

    def test_stale_belts_are_ordered_up_and_nothing_else(self):
        r = FakeLink()
        lines = self.fresh(r)
        self.assertEqual(len(r.sent), 1)
        self.assertIn('transport-belt\\", 1.5, 1.5]', r.sent[0])     # JSON inside a Lua string
        self.assertIn('underground-belt\\", 3.5, 1.5]', r.sent[0])
        self.assertNotIn("2.5", r.sent[0])
        self.assertIn("2 of 2 ordered up (2 belts, 0 inserters; pipe, steel-plate)", lines[0])

    def test_an_inserter_stuck_with_an_unused_item_goes_too(self):
        r = FakeLink(hands='[["inserter", 5.5, 1.5, "iron-gear-wheel"]]', ordered="3")
        lines = self.fresh(r)
        self.assertIn('inserter\\", 5.5, 1.5]', r.sent[0])
        self.assertIn("3 of 3 ordered up (2 belts, 1 inserter; iron-gear-wheel, pipe, steel-plate)",
                      lines[0])
        self.assertIn("inserter 5.5,1.5 holds iron-gear-wheel", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
