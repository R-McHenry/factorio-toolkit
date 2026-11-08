"""3.0, Bob's adjustable inserters (Sea Block; assessment-20261101/PLAN-BOB-INSERTERS.md): every
inserter takes its own pickup and drop vectors. From the start each is any of the 4 tiles beside it
(an inserter turns a corner); bob-long-inserters-1 lets any inserter reach 2 tiles. The stock read
gives the techs, the router lays corner and range-2 hands where the force has them, a corner
swings in half the ticks, the paste writes the vectors and reads them back unchanged, and a vector
the force lacks is a needs-research line."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import arms, codec, connect, flow, lanes, route, settings, supply
from fkcore import fkp as fkpmod
from fkcore.catalog import Catalog
from fkcore.steiner import TapSink

CAT = Catalog.load()

#: a requester chest diagonal to a provider: no straight inserter links them
DIAG = """module Diag size 8x8 {
  q  = Chest<requester, item=iron-plate, rate=0.5> @(2, 2)
  b  = Chest<provider> @(3, 3)
  net x: q -> b
}
h = Diag @(2, 2)
"""
#: two chests three tiles apart: one inserter between them reaches 1 and 2 (0.5/s: one hand carries it)
FAR = """module Far size 10x6 {
  q  = Chest<requester, item=iron-plate, rate=0.5> @(1, 2)
  b  = Chest<provider> @(4, 2)
  net x: q -> b
}
h = Far @(2, 2)
"""


def _row(name, stock, enabled):
    return {"entity": name, "item": name, "stock": stock, "known": True, "enabled": enabled}


def _ins(key, x, y, d, **attrs):
    return fkpmod.Entity(key, "inserter", x, y, d, dict(attrs))


class Paper(unittest.TestCase):
    """A paper Sea Block game (FK_PACK=seablock) with an ``out/avail.json``."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkbob-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.makedirs(os.path.join(self.dir, "out"))
        old = os.environ.get("FK_PACK")
        self.addCleanup(lambda: os.environ.pop("FK_PACK", None) if old is None
                        else os.environ.__setitem__("FK_PACK", old))

    def route(self, text, techs=None, pack="seablock"):
        os.environ["FK_PACK"] = pack
        for name, body in (("t.fk", text),
                           ("nauvis.surface", "surface nauvis\nterrain none\n"
                                              "place t = t plot 0,0 30x30\n"),
                           ("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\n"
                                                "elaborate\nplace --keep pinned\n"
                                                "route --only stale --hand any\nwrite_layout\n")):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        if techs is not None:
            with open(os.path.join(self.dir, "out", "avail.json"), "w", encoding="utf-8") as fh:
                json.dump({"tick": 1, "force": "player", "surface": "nauvis", "networks": 1,
                           "entities": [_row("inserter", 50, True),
                                        _row("fast-inserter", 0, False)],
                           "recipes": [], "research": {"techs": techs}}, fh)
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        return ctx.layouts["t"]

    def laid(self, lay):
        return [e for e in lay.entities.values() if e.owner.startswith("~")]


class CapabilityTest(Paper):
    def test_nothing_read_is_the_base_set(self):
        os.environ["FK_PACK"] = "seablock"
        self.assertEqual(arms.of(supply.Supply(0, "", "", 0)), arms.Arms(1, 4, False))
        self.assertEqual(arms.of(packed=True, sup=supply.Supply(0, "", "", 0)).range, 1)

    def test_the_base_game_takes_no_vectors(self):
        os.environ["FK_PACK"] = ""
        self.assertIsNone(arms.of())

    def test_the_techs_widen_it(self):
        sup = supply.from_raw({"research": {"techs": {arms.LONG_1: True, arms.MORE_1: True,
                                                      arms.LONG_2: False}}})
        got = arms.of(sup, packed=True)
        self.assertEqual((got.range, got.ways, got.near), (2, 8, False))
        self.assertTrue(got.allows((1, 1)) and got.allows((0, 2)))
        self.assertFalse(got.allows((0, 3)) or got.allows((1, 2)))
        # the game writes an empty table as a list
        self.assertEqual(arms.of(supply.from_raw({"research": {"techs": []}}), packed=True).range, 1)

    def test_the_stock_read_reads_the_techs_and_avail_keeps_them(self):
        lua = supply.lua_read("player", "nauvis", ["inserter"], [], "t")
        for t in arms.TECHS:
            self.assertIn(t, lua)
        self.assertIn("research.techs", lua)
        from fkcore import avail
        sup = supply.from_raw({"tick": 3, "research": {"techs": {arms.LONG_1: True}}})
        avail.save(self.dir, sup, "test")
        self.addCleanup(avail.install, None)
        self.assertEqual(avail.load(self.dir).sup.research["techs"], {arms.LONG_1: True})


class ModelTest(unittest.TestCase):
    def test_a_corner_inserter_picks_north_and_drops_east(self):
        ents = [fkpmod.Entity("a", "wooden-chest", 0.5, 0.5, None, {}),
                _ins("i", 0.5, 1.5, 0, pick="0,-1", drop="1,0"),
                fkpmod.Entity("b", "wooden-chest", 1.5, 1.5, None, {})]
        g = connect.graph(ents, CAT)
        self.assertEqual(g.inserter_tiles("i"), ((0, 0), (1, 1)))
        self.assertIn(("i", "pickup"), g.succ["a"])
        self.assertIn(("b", "drop"), g.succ["i"])

    def test_no_vectors_is_the_direction_and_reach(self):
        g = connect.graph([_ins("i", 2.5, 2.5, 4),
                           fkpmod.Entity("l", "long-handed-inserter", 6.5, 2.5, 0, {})], CAT)
        self.assertEqual(g.inserter_tiles("i"), ((3, 2), (1, 2)))
        self.assertEqual(g.inserter_tiles("l"), ((6, 0), (6, 4)))

    def test_canon_keeps_both_or_neither(self):
        self.assertEqual(arms.canon("inserter", 0, (0, -1), (0, 1)), {})
        self.assertEqual(arms.canon("long-handed-inserter", 4, (2, 0), (-2, 0)), {})
        self.assertEqual(arms.canon("inserter", 0, (0, -1), (1, 0)), {"pick": "0,-1", "drop": "1,0"})

    def test_the_fkp_keeps_them(self):
        lay = fkpmod.Layout("factory", "t")
        lay.add(_ins("~x/i0", 4.5, 5.5, 0, net="x", pick="0,-1", drop="1,0"))
        back = fkpmod.loads(fkpmod.dumps(lay)).entities["~x/i0"]
        self.assertEqual((back.attrs["pick"], back.attrs["drop"]), ("0,-1", "1,0"))

    def test_a_turned_plot_turns_the_vectors(self):
        self.assertEqual(arms.turned({"pick": "0,-1", "drop": "1,0"}, 1),
                         {"pick": "1,0", "drop": "0,1"})
        self.assertEqual(arms.turned({"pick": "0,-2", "drop": "1,0"}, 2),
                         {"pick": "0,2", "drop": "-1,0"})
        plain = {"net": "x"}
        self.assertIs(arms.turned(plain, 1), plain)

    def test_the_ground_rules_see_the_vectors(self):
        got = route._hand_tiles(CAT, [_ins("~x/i0", 4.5, 5.5, 0, net="x", pick="0,-1",
                                           drop="2,0")])
        self.assertEqual(set(got), {(4, 4), (6, 5)})


class RouterTest(Paper):
    def test_a_corner_inserter_links_two_diagonal_chests(self):
        ins = [e for e in self.laid(self.route(DIAG, techs={})) if "inserter" in e.name]
        self.assertEqual(len(ins), 1)
        self.assertEqual((ins[0].attrs["pick"], ins[0].attrs["drop"]), ("0,-1", "1,0"))
        self.assertFalse([e for e in self.laid(self.route(DIAG, techs={})) if "belt" in e.name])

    def test_the_base_game_lays_a_belt_there(self):
        laid = self.laid(self.route(DIAG, pack=""))
        self.assertTrue(any("belt" in e.name for e in laid))
        self.assertFalse(any("pick" in e.attrs for e in laid))

    def test_long_1_lets_a_plain_inserter_reach_two(self):
        laid = self.laid(self.route(FAR, techs={arms.LONG_1: True}))
        self.assertEqual([e.name for e in laid], ["inserter"])
        e, = laid
        v = arms.vectors(e.name, e.dir, e.attrs)
        self.assertEqual(sorted(max(abs(c) for c in t) for t in v), [1, 2])

    def test_without_long_1_no_hand_reaches_two(self):
        # fair play: the force has range 1, so a belt carries it between corner hands
        lay = self.route(FAR, techs={})
        laid = self.laid(lay)
        for e in laid:
            if "pick" in e.attrs:
                self.assertIsNone(arms.needs(arms.Arms(), *arms.vectors(e.name, e.dir, e.attrs)))
        self.assertTrue(any("belt" in e.name for e in laid))
        self.assertEqual(connect.connect(lay, CAT).nets["h/x"].status, "connected")

    def test_tap_sink_offers_corners_after_the_straight_ones(self):
        sink = TapSink("m", (5, 0, 8, 3), 1, ("inserter",), arms=arms.Arms())
        got = sink.taps_at((3, 1), lambda q: True)
        self.assertEqual(got, [((4, 1), "inserter", 12, None)])      # straight, no vectors
        # a belt off the machine's corner: only a corner inserter reaches it
        got = sink.taps_at((4, -1), lambda q: True)
        self.assertEqual(sorted(q for q, *_ in got), [(4, 0), (5, -1)])
        for q, _n, _d, (pick, drop) in got:
            self.assertEqual((q[0] + pick[0], q[1] + pick[1]), (4, -1))
            self.assertTrue(sink.inside((q[0] + drop[0], q[1] + drop[1])))
        self.assertEqual(TapSink("m", (5, 0, 8, 3), 1, ("inserter",)).taps_at((4, -1), lambda q: True),
                         [])
        # the base game: as before
        self.assertEqual(TapSink("m", (5, 0, 8, 3), 1, ("inserter",)).taps_at((3, 1), lambda q: True),
                         [((4, 1), "inserter", 12, None)])

    def test_k_taps_still_lay(self):
        # 3.0's k-inserter work keeps working with the extra spots (test_route_taps' cable)
        cable = """module Cab size 20x14 {
  q  = Chest<requester, item=copper-plate, rate=2> @(1, 6)
  a1 = Assembler<recipe=copper-cable> @(7, 2)
  a2 = Assembler<recipe=copper-cable> @(7, 9)
  b  = Chest<provider> @(18, 6)
  net cu: q -> a1, a2
  net k: a1, a2 -> b
}
h = Cab @(2, 2)
"""
        lay = self.route(cable, techs={})
        k = route._TAPS.get(("h/k", "h/a1/m0"), 1)
        out = sum(1 for e in self.laid(lay) if "inserter" in e.name and e.owner == "~h/k")
        self.assertGreaterEqual(out, 2 * k + 1)
        rep = connect.connect(lay, CAT)
        self.assertEqual(rep.nets["h/k"].status, "connected", rep.lines())


class RatesTest(unittest.TestCase):
    def test_a_corner_swings_in_half_the_ticks(self):
        # measured on a Sea Block laptop server (2026-11-02): rotation 0.02, 1.198/s and 2.5/s
        self.assertAlmostEqual(lanes.inserter_rate("x", cat=None, turn=0.5) or 0, 0)
        cat = _FakeCat({"inserter": 0.02, "fast-inserter": 0.06})
        self.assertAlmostEqual(lanes.inserter_rate("inserter", cat=cat), 1.2, 3)
        self.assertAlmostEqual(lanes.inserter_rate("inserter", cat=cat, turn=0.25), 2.5, 3)
        self.assertAlmostEqual(lanes.inserter_rate("fast-inserter", cat=cat, turn=0.25), 7.5, 3)
        self.assertEqual(arms.turn((0, -1), (1, 0)), 0.25)
        self.assertEqual(arms.turn((0, -2), (0, 1)), 0.5)

    def test_the_lane_graph_rates_a_corner_inserter_faster(self):
        ents = [fkpmod.Entity("a", "wooden-chest", 0.5, 0.5, None, {}),
                _ins("c", 0.5, 1.5, 0, pick="0,-1", drop="1,0"),
                fkpmod.Entity("b", "wooden-chest", 1.5, 1.5, None, {}),
                fkpmod.Entity("a2", "wooden-chest", 4.5, 0.5, None, {}),
                _ins("s", 4.5, 1.5, 0),
                fkpmod.Entity("b2", "wooden-chest", 4.5, 2.5, None, {})]
        lg = lanes.build(ents, CAT)
        self.assertGreater(lg.nodes[("c", "")].cap, 1.9 * lg.nodes[("s", "")].cap)

    def test_a_corner_drop_onto_a_belt_fills_the_far_lane(self):
        # the inserter west of a north belt drops east: across it, the far (right) lane
        ents = [fkpmod.Entity("a", "wooden-chest", 0.5, 0.5, None, {}),
                _ins("c", 0.5, 1.5, 0, pick="0,-1", drop="1,0"),
                fkpmod.Entity("t", "transport-belt", 1.5, 1.5, 0, {})]
        lg = lanes.build(ents, CAT)
        self.assertEqual([e.dst for e in lg.out[("c", "")]], [("t", "R")])


class _FakeCat:
    def __init__(self, rot):
        self.rot = rot

    def has_entity(self, name):
        return name in self.rot

    def entity(self, name):
        return {"rotation_speed": self.rot[name]}


class PasteTest(unittest.TestCase):
    def test_the_blueprint_carries_them_and_reads_them_back(self):
        lay = fkpmod.Layout("factory", "t")
        lay.add(_ins("~x/i0", 4.5, 5.5, 0, net="x", pick="0,-1", drop="1,0"))
        lay.add(_ins("~x/i1", 8.5, 5.5, 12, net="x", pick="-1,0", drop="2,0"))
        lay.add(_ins("~x/i2", 9.5, 9.5, 4, net="x"))
        rows = codec.rows_of(lay)
        bp = json.loads(codec.zlib.decompress(codec.base64.b64decode(
            codec.blueprint(rows)[1:])).decode())["blueprint"]["entities"]
        self.assertEqual(bp[0]["pickup_position"], [0, -1])
        self.assertEqual(bp[0]["drop_position"], [1.2, 0])
        self.assertEqual(bp[1]["drop_position"], [2.2, 0])
        self.assertNotIn("pickup_position", bp[2])
        self.assertNotIn("pick", bp[0]["tags"].get("fkp", {}))
        back = {r["src"]: r["attrs"] for r in codec.read_blueprint(codec.blueprint(rows))[0]}
        self.assertEqual((back["~x/i0"]["pick"], back["~x/i0"]["drop"]), ("0,-1", "1,0"))
        self.assertEqual(back["~x/i1"]["drop"], "2,0")
        self.assertNotIn("pick", back["~x/i2"])

    def test_the_games_own_export_reads_back(self):
        # what the laptop server exported (2026-11-02): only the vector that is not the default,
        # the drop as the game keeps it
        game = [{"entity_number": 1, "name": "inserter", "position": {"x": 0.5, "y": 0.5},
                 "drop_position": [1.19921875, 0]},
                {"entity_number": 2, "name": "inserter", "position": {"x": 0.5, "y": 4.5},
                 "direction": 4, "drop_position": [0, -3.203125], "pickup_position": [0, 2]},
                {"entity_number": 3, "name": "inserter", "position": {"x": 3.5, "y": 0.5},
                 "direction": 4}]
        text = "0" + codec.base64.b64encode(codec.zlib.compress(json.dumps(
            {"blueprint": {"item": "blueprint", "entities": game}}).encode())).decode()
        rows, _d, _w = codec.parse_blueprint(text)
        self.assertEqual(rows[0]["attrs"], {"pick": "0,-1", "drop": "1,0"})
        self.assertEqual(rows[1]["attrs"], {"pick": "0,2", "drop": "0,-3"})
        self.assertEqual(rows[2]["attrs"], {})
        self.assertNotIn("config", rows[0]["attrs"])

    def test_the_settings_diff_sees_no_change_once_built(self):
        row = {"src": "~x/i0", "name": "inserter", "x": 0.5, "y": 0.5, "direction": 0,
               "attrs": {"pick": "0,-1", "drop": "1,0"}}
        want = settings._fields(codec.entity_json(row, 1), ())
        have = settings._fields({"entity_number": 1, "name": "inserter",
                                 "position": {"x": 0.5, "y": 0.5},
                                 "drop_position": {"x": 1.19921875, "y": 0}}, None)
        self.assertEqual(want, have)
        self.assertEqual(want["vectors"], "pick=0,-1 drop=1,0")
        plain = settings._fields({"entity_number": 1, "name": "inserter",
                                  "position": {"x": 0.5, "y": 0.5}}, None)
        self.assertNotIn("vectors", plain)

    def test_a_single_ghost_takes_world_positions(self):
        lua = __import__("fkcore.link", fromlist=["x"]).lua_ghosts("nauvis", "player", [])
        self.assertIn("pickup_position = 1, drop_position = 1", lua)
        self.assertIn("g.position.x + v[1]", lua)


class FairPlayTest(unittest.TestCase):
    def test_only_researched_vectors(self):
        base = arms.Arms()
        self.assertIsNone(arms.needs(base, (0, -1), (1, 0)))
        self.assertEqual(arms.needs(base, (0, -1), (2, 0)), arms.LONG_1)
        self.assertEqual(arms.needs(arms.Arms(2), (0, -3), (0, 1)), arms.LONG_2)
        self.assertEqual(arms.needs(base, (1, -1), (0, 1)), arms.MORE_1)
        got = arms.locked([_ins("a", 0.5, 0.5, 0, pick="0,-1", drop="2,0"),
                           _ins("b", 2.5, 0.5, 0, pick="0,-1", drop="1,0"),
                           _ins("c", 4.5, 0.5, 0)], base)
        self.assertEqual(got, {arms.LONG_1: ["a"]})
        self.assertEqual(arms.locked([_ins("a", 0.5, 0.5, 0, pick="0,-1", drop="2,0")], None), {})

    def test_pairs_lay_the_force_range_only(self):
        for pick, drop in arms.pairs(arms.Arms()):
            self.assertIsNone(arms.needs(arms.Arms(), pick, drop))
        self.assertTrue(any(max(map(abs, d)) == 2 for _p, d in arms.pairs(arms.Arms(2))))
        first = arms.pairs(arms.Arms(2), straight=False)[0]
        self.assertEqual(arms.turn(*first), 0.25)          # a corner at range 1 first


if __name__ == "__main__":
    unittest.main()
