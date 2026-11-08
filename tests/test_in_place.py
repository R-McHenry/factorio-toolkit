"""Settings changed in place (2.1, Rory 2026-10-31): the codec's reset control behaviour, explicit
defaults equal to absent ones, upgrades in place and the wire pass (fkcore.wires). Offline: the
game's side is what a laptop server (2.0.77) did; tools/laptop_server.py defaults, settings and
robots run the same in a game."""
import json
import unittest
from unittest import mock

from fkcore import apply as applymod, codec, compose, fkp, link, settings, wires
from fkcore.catalog import Catalog
from fkcore.sense import SenseReport, Verdict

CAT = Catalog.load()


def row(src, name, x, y, d=None, **attrs):
    return {"src": src, "name": name, "x": x, "y": y, "direction": d, "attrs": attrs}


class CodecTest(unittest.TestCase):
    def test_a_machine_with_nothing_set_gets_the_reset(self):
        for name in ("inserter", "fast-inserter", "transport-belt", "assembling-machine-2",
                     "electric-furnace", "pump", "small-lamp", "chemical-plant"):
            self.assertEqual(codec.entity_json(row("a/b", name, 0.5, 0.5), 1)["control_behavior"],
                             codec.RESET_CB, name)

    def test_what_a_paste_clears_itself_gets_no_field(self):
        # requests, a limit, a storage filter, a combinator's settings: an absent field clears
        # them (measured), and a pole, an underground or a drill has nothing to reset
        for name in ("requester-chest", "wooden-chest", "storage-chest", "constant-combinator",
                     "small-electric-pole", "underground-belt", "electric-mining-drill"):
            self.assertNotIn("control_behavior", codec.entity_json(row("a/b", name, 0.5, 0.5), 1),
                             name)

    def test_a_design_setting_is_written_whole_without_the_reset(self):
        got = codec.entity_json(row("a/b", "inserter", 0.5, 0.5, 4, **{"if": "iron-plate<5"}), 1)
        self.assertEqual(got["control_behavior"]["circuit_condition"]["constant"], 5)
        self.assertTrue(got["control_behavior"]["circuit_enabled"])
        lit = row("a/b", "inserter", 0.5, 0.5, 4, config=codec.config_text(
            {"control_behavior": {"circuit_read_hand_contents": True}}))
        self.assertEqual(codec.entity_json(lit, 1)["control_behavior"],
                         {"circuit_read_hand_contents": True})

    def test_the_reset_reads_back_as_nothing(self):
        lay = fkp.loads("fkp 1 factory f\nsize 4x2\ne ~n/i0 inserter 0.5,0.5 E net=n\n"
                        "e ~n/i1 inserter 1.5,0.5 E net=n if=iron-plate<5\n")
        bp = codec.fkp_to_blueprint(lay)
        back = codec.blueprint_to_fkp(bp)
        self.assertEqual(fkp.dumps(back), fkp.dumps(lay))
        # as the game exports it: the false flag dropped
        self.assertTrue(codec.is_reset({"circuit_condition": {"comparator": "<", "constant": 1}}))
        self.assertFalse(codec.is_reset({"circuit_condition": {"comparator": "<", "constant": 1,
                                                               "first_signal": {"name": "coal"}}}))


class DefaultsTest(unittest.TestCase):
    """An explicit default compares equal to an absent field (fkcore.settings)."""

    def test_the_design_with_the_reset_is_nothing_set(self):
        want = settings._fields(codec.entity_json(row("a/b", "inserter", 0.5, 0.5, 4), 1))
        self.assertEqual(want, {})

    def test_the_games_exports_after_a_paste(self):
        # what the laptop server's export showed after the 2.1 paste (check_defaults)
        for cb in ({"circuit_condition": {"comparator": "<", "constant": 1}},
                   {"circuit_contents_read_mode": 0},
                   {"red_signal": {"type": "virtual", "name": "signal-red"},
                    "green_signal": {"type": "virtual", "name": "signal-green"},
                    "blue_signal": {"type": "virtual", "name": "signal-blue"},
                    "rgb_signal": {"type": "virtual", "name": "signal-white"}},
                   {"is_on": True, "sections": {"sections": [{"index": 1}]}}):
            self.assertEqual(settings._fields({"control_behavior": cb}), {}, cb)
        self.assertEqual(settings._fields({"filter_mode": "whitelist", "use_filters": False,
                                           "request_filters": {"sections": [{"index": 1}]}}), {})

    def test_a_set_condition_or_read_mode_still_differs(self):
        self.assertNotEqual(settings._fields({"control_behavior": {
            "circuit_condition": {"comparator": "<", "constant": 5,
                                  "first_signal": {"name": "iron-plate"}}}}), {})
        self.assertEqual(settings._fields({"control_behavior": {
            "circuit_read_hand_contents": True, "circuit_contents_read_mode": 1}}),
            {"control_behavior": {"circuit_read_hand_contents": True,
                                  "circuit_contents_read_mode": 1}})


def end(name, x, y, c):
    return (name, float(x), float(y), c)


class WiresTest(unittest.TestCase):
    ROWS = [row("p/p0", "small-electric-pole", 2.5, 2.5), row("p/p1", "small-electric-pole", 7.5, 2.5),
            row("p/p2", "small-electric-pole", 5.5, 6.5),
            row("m/c0", "wooden-chest", 10.5, 2.5, wire="1,i0,1"),
            row("m/i0", "inserter", 11.5, 2.5, 4)]

    def want(self):
        return wires.design_wires(self.ROWS, None, CAT)

    def test_the_designs_wires(self):
        P0, P1, P2 = (end("small-electric-pole", *xy, 5) for xy in ((2.5, 2.5), (7.5, 2.5),
                                                                    (5.5, 6.5)))
        got = self.want()
        self.assertEqual(len(got), 3)                    # two copper (a spanning tree), one red
        self.assertIn(wires._wire(P1, P2), got)
        self.assertIn(wires._wire(end("wooden-chest", 10.5, 2.5, 1), end("inserter", 11.5, 2.5, 1)),
                      got)
        self.assertNotIn(wires._wire(P0, P2) if wires._wire(P0, P1) in got else
                         wires._wire(P0, P1), got)

    def test_plan_adds_missing_cuts_extra_and_leaves_the_world_alone(self):
        want = self.want()
        ends = {(r["name"], r["x"], r["y"]) for r in self.ROWS}
        P0, P1, P2 = (end("small-electric-pole", *xy, 5) for xy in ((2.5, 2.5), (7.5, 2.5),
                                                                    (5.5, 6.5)))
        world = end("small-electric-pole", 1.5, 8.5, 5)              # the world's own pole
        have = set(list(want)[:1]) | {wires._wire(P0, P1), wires._wire(P0, P2),
                                      wires._wire(P2, world)}
        add, cut = wires.plan(want, have, ends, (0, 0, 20, 20))
        self.assertEqual(set(add), want - have)
        extra = {w for w in have - want if world not in w}
        self.assertEqual(set(cut), extra)
        self.assertTrue(all(world not in w for w in cut))
        # a design wire with no end in the area is no business of this pass
        add, _cut = wires.plan(want, set(), ends, (100, 100, 110, 110))
        self.assertEqual(add, [])

    def test_world_wires_keep_each_once(self):
        data = {"w": [["inserter", 11.5, 2.5, 1, "wooden-chest", 10.5, 2.5, 1],
                      ["wooden-chest", 10.5, 2.5, 1, "inserter", 11.5, 2.5, 1]]}
        self.assertEqual(len(wires.world_wires(data)), 1)

    def test_the_count_line(self):
        self.assertIsNone(wires.Pass().line())
        self.assertEqual(wires.Pass(added=3, cut=1).line(), "wires: 3 added, 1 cut")
        self.assertIn("1 the game refused", wires.Pass(refused=1).line())
        self.assertTrue(wires.Pass(error="LinkError: x").line().startswith("wires: not matched"))

    def test_run_edits_and_names_a_cut_circuit_wire(self):
        lay = fkp.loads("fkp 1 factory f\nsize 12x6\ne p/p0 small-electric-pole 0.5,0.5\n"
                        "e p/p1 small-electric-pole 4.5,0.5\ne m/c0 wooden-chest 2.5,2.5\n"
                        "e m/i0 inserter 3.5,2.5 E\n")
        s = compose.compose(fkp.loads("fkp 1 surface lab\nplot f at 0,0 rot 0 size 12x6\n"),
                            {"f": lay}, CAT)
        world = [["wooden-chest", 2.5, 2.5, 1, "inserter", 3.5, 2.5, 1]]   # by hand
        calls = []

        class R:
            def lua(self, body):
                calls.append(body)
                ops = json.loads(json.loads(body.split("json_to_table(", 1)[1].split(")) do", 1)[0]))
                return json.dumps([1] * len(ops))
        with mock.patch.object(link, "read_output", return_value={"w": world}):
            got = wires.run(R(), s, CAT, (0, 0, 12, 6))
        self.assertEqual((got.added, got.cut), (1, 1))     # the poles' wire, the hand's red one
        self.assertEqual(got.line(), "wires: 1 added, 1 cut")
        self.assertEqual(got.hand, ["a red wire between inserter at 3.5,2.5 and wooden-chest at "
                                    "2.5,2.5, which the design doesn't have: cut"])
        self.assertTrue(all("register" not in c and "on_event" not in c for c in calls))

    def test_a_partial_apply_lays_the_whole_designs_pole_wires(self):
        lay = fkp.loads("fkp 1 factory f\nsize 12x2\ne p/p0 small-electric-pole 0.5,0.5\n"
                        "e p/p1 small-electric-pole 3.5,0.5\ne p/p2 small-electric-pole 6.5,0.5\n")
        s = compose.compose(fkp.loads("fkp 1 surface lab\nplot f at 0,0 rot 0 size 12x2\n"),
                            {"f": lay}, CAT)
        poles = applymod.design_poles(s, CAT)
        rows = applymod.scope_rows(s)
        self.assertEqual(applymod.pole_wires(rows, s, CAT, poles), codec.pole_wires(rows, CAT))
        two = [rows[0], rows[2]]           # p0 and p2 are in reach, but the design wires each to p1
        self.assertEqual(codec.pole_wires(two, CAT), [(0, 1)])
        self.assertEqual(applymod.pole_wires(two, s, CAT, poles), [])


class UpgradeTest(unittest.TestCase):
    def setUp(self):
        lay = fkp.loads("fkp 1 factory f\nsize 6x2\ne ~n/i0 fast-inserter 0.5,0.5 E net=n\n"
                        "e box/c0 iron-chest 2.5,0.5\n")
        self.s = compose.compose(fkp.loads("fkp 1 surface lab\nplot f at 0,0 rot 0 size 6x2\n"),
                                 {"f": lay}, CAT)

    def before(self):
        return SenseReport([0, 0, 6, 2], 1, [
            Verdict("other-entity", "fast-inserter", 0.5, 0.5, "lab:f/~n/i0", "inserter stands there",
                    under=[("inserter", 0.5, 0.5, None, False, True)]),
            Verdict("other-entity", "iron-chest", 2.5, 0.5, "lab:f/box/c0",
                    "wooden-chest stands there",
                    under=[("wooden-chest", 2.5, 0.5, None, True, True)]),     # a ghost: no
            Verdict("unowned", "inserter", 0.5, 0.5, "lab:f/~n/i0", "dropped", None, "own")],
            [], [], [], [], {})

    def test_candidates_stand_on_the_design_position_built(self):
        got = applymod.upgrade_candidates(self.before(), self.s)
        self.assertEqual([(c["old"], c["new"], c["dir"]) for c in got],
                         [("inserter", "fast-inserter", 4)])

    def test_the_lua_asks_the_game_for_its_groups_and_sizes(self):
        lua = applymod.lua_upgrade("lab", "lab", applymod.upgrade_candidates(self.before(), self.s))
        for word in ("fast_replaceable_group", "collision_box", "order_upgrade", "to_be_upgraded"):
            self.assertIn(word, lua)
        self.assertNotIn("register", lua)

    def test_an_upgraded_one_is_not_ordered_out_and_is_reported(self):
        ordered = []

        class R:
            def lua(self, body):
                if "order_upgrade" in body:
                    return '["up"]'
                if "order_deconstruction" in body:
                    data = json.loads(json.loads(body.split("json_to_table(", 1)[1]
                                                 .split(")) do", 1)[0]))
                    ordered.extend(tuple(t) for t in data)
                    return str(len(data))
                return "0"
        before = self.before()
        cap = {"tick": 1, "things": [{"n": "inserter", "x": 0.5, "y": 0.5, "g": False, "dc": False},
                                     {"n": "iron-chest", "x": 2.5, "y": 0.5, "g": True}]}
        with mock.patch.object(applymod, "diff", return_value=before), \
                mock.patch.object(link, "snapshot", return_value=cap), \
                mock.patch.object(link, "paste", return_value="1"), \
                mock.patch.object(wires, "run", return_value=wires.Pass()), \
                mock.patch.object(link, "ghosts") as ghosts:
            rep = applymod.apply(R(), self.s, CAT, force="lab",
                                 policy={"plots": "keep"})
        self.assertEqual(rep.upgraded, [("lab:f/~n/i0", "inserter", "fast-inserter")])
        self.assertEqual(ordered, [])
        self.assertEqual((rep.present, rep.placed_alone), (2, 0))
        ghosts.assert_not_called()
        self.assertIn("upgraded 1 (robots swap them; settings, wires and contents stay): "
                      "f/~n/i0 inserter -> fast-inserter", "\n".join(rep.lines()))


if __name__ == "__main__":
    unittest.main()
