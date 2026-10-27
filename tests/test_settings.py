"""2.0.12 (Rory, 2026-10-24: "it needs to be able to see my circuit changes and know that it is
overriding them too"): a standing entity's settings against the design's (fkcore.settings), as
hand edits (sense.hand_edits). Offline: the game's side is its blueprint export, as a laptop
server (2.0.77) wrote it; tools/laptop_server.py settings runs the whole thing in a game."""
import unittest

from fkcore import codec, sense, settings
from fkcore.sense import Verdict

I0 = ("inserter", 5.5, 5.5)
I1 = ("inserter", 5.5, 7.5)
C0 = ("requester-chest", 8.5, 5.5)


def rows():
    return [{"src": "m/i0", "name": "inserter", "x": 5.5, "y": 5.5, "direction": 4,
             "attrs": {"logistic": "iron-plate<50"}},
            {"src": "m/i1", "name": "inserter", "x": 5.5, "y": 7.5, "direction": 4, "attrs": {}},
            {"src": "m/c0", "name": "requester-chest", "x": 8.5, "y": 5.5, "direction": None,
             "attrs": {"config": codec.config_text({"request_filters": {"sections": [{
                 "index": 1, "filters": [{"index": 1, "name": "iron-plate", "quality": "normal",
                                          "comparator": "=", "count": 100}]}]}})}}]


def game(i0_condition=None, request=None, wire=False):
    """``lua_read``'s file, with the fields the game exported (laptop server, 2026-10-24)."""
    cb0 = {"stack_control_input_signal": {"type": "virtual", "name": "signal-S"}}
    if i0_condition:
        cb0.update(connect_to_logistic_network=True, logistic_condition=i0_condition)
    e0 = {"entity_number": 1, "name": "inserter", "direction": 4, "control_behavior": cb0}
    e1 = {"entity_number": 3, "name": "inserter", "direction": 4,
          "control_behavior": {"stack_control_input_signal": {"type": "virtual",
                                                              "name": "signal-S"}}}
    if wire:
        e0["wires"], e1["wires"] = [[1, 1, 3, 1]], [[3, 1, 1, 1]]
    c0 = {"entity_number": 2, "name": "requester-chest",
          "request_filters": {"sections": [request or {"index": 1}]}}
    return {"rows": [{"n": 1, "name": "inserter", "x": 5.5, "y": 5.5, "e": e0},
                     {"n": 2, "name": "requester-chest", "x": 8.5, "y": 5.5, "e": c0},
                     {"n": 3, "name": "inserter", "x": 5.5, "y": 7.5, "e": e1}]}


DESIGNED = {"first_signal": {"name": "iron-plate"}, "constant": 50, "comparator": "<"}
REQUEST = {"index": 1, "filters": [{"index": 1, "name": "iron-plate", "quality": "normal",
                                    "comparator": "=", "count": 100}]}
VERDICTS = [Verdict("ok", "inserter", 5.5, 5.5, "nauvis:mall/m/i0"),
            Verdict("ok", "inserter", 5.5, 7.5, "nauvis:mall/m/i1"),
            Verdict("ok", "requester-chest", 8.5, 5.5, "nauvis:mall/m/c0")]


def drifts(**kw):
    return settings.drifts(settings.design(rows(), None), settings.live(game(**kw)), VERDICTS,
                           {settings._at(*I0): "rory_618"})


class SettingsTest(unittest.TestCase):
    def test_as_designed_is_no_change(self):
        # the game's defaults (signal-S on an inserter, an empty request section) are no setting
        self.assertEqual(drifts(i0_condition=DESIGNED, request=REQUEST), [])

    def test_a_changed_condition_and_request(self):
        got = drifts(i0_condition={"first_signal": {"name": "copper-plate"}, "constant": 7,
                                   "comparator": ">"},
                     request={"index": 1, "filters": [{"index": 1, "name": "copper-plate",
                                                       "count": 5}]})
        self.assertEqual([d.line() for d in got], [
            "Someone changed (the game names no one: a script, or the map editor) requester-chest "
            "at 8.5,5.5 (mall/m/c0): requests copper-plate 5 (the paste sets requests iron-plate "
            "100)",
            "rory_618 changed inserter at 5.5,5.5 (mall/m/i0): logistic=copper-plate>7 (the paste "
            "sets logistic=iron-plate<50)"])

    def test_a_condition_or_request_the_design_lacks(self):
        got = drifts(i0_condition=DESIGNED, request={"index": 1})
        self.assertEqual(got[0].line().split("): ", 1)[1],
                         "nothing set (the paste sets requests iron-plate 100)")
        want = settings.design(rows()[:2] + [dict(rows()[2], attrs={})], None)
        have = settings.live(game(i0_condition=DESIGNED, request=REQUEST))
        got = settings.drifts(want, have, VERDICTS, {})
        self.assertTrue(got[0].line().endswith("requests iron-plate 100 (the design has none: the "
                                               "paste clears it)"), got[0].line())

    def test_a_wire_added_by_hand_stays(self):
        got = drifts(i0_condition=DESIGNED, request=REQUEST, wire=True)
        self.assertEqual([d.line().split("): ", 1)[1] for d in got],
                         ["red wire to inserter at 5.5,7.5 (the design has none: the paste "
                          "leaves it)",
                          "red wire to inserter at 5.5,5.5 (the design has none: the paste "
                          "leaves it)"])

    def test_only_what_stands_where_the_design_has_it(self):
        ghost = [Verdict("ghost", "inserter", 5.5, 5.5, "nauvis:mall/m/i0")] + VERDICTS[1:]
        got = settings.drifts(settings.design(rows(), None), settings.live(game(request=REQUEST)),
                              ghost, {})
        self.assertEqual(got, [])

    def test_they_are_hand_edits(self):
        rep = sense.SenseReport([0, 0, 9, 9], 1, [], [], [], [], [], {})
        rep.settings = drifts(i0_condition={"first_signal": {"name": "copper-plate"},
                                            "constant": 7, "comparator": ">"}, request=REQUEST)
        self.assertEqual(sense.hand_edits(rep), [
            "rory_618 changed inserter at 5.5,5.5 (mall/m/i0): logistic=copper-plate>7 (the paste "
            "sets logistic=iron-plate<50)"])
        self.assertIn("settings: 1 standing entities set otherwise than the design (hand edits)",
                      rep.lines())

    def test_describe_in_the_sources_words(self):
        fields = codec.control_behavior({"if": "iron-gear-wheel>=100", "filter": "iron-plate|coal",
                                         "read": "hand"})
        self.assertEqual(settings.describe(codec._normal(fields)),
                         "if=iron-gear-wheel>=100; read=hand; filter=iron-plate|coal")
        self.assertEqual(settings.describe({"bar": 0, "recipe": "pipe"}),
                         "recipe pipe; limit 0 slots")
        self.assertEqual(settings._clean({"bar": 0, "constant": 0, "use_filters": False}),
                         {"bar": 0, "constant": 0})


if __name__ == "__main__":
    unittest.main()
