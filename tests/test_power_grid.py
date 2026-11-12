"""The world's grid as a global parameter, and pole kinds as an input (PLAN-POWER P1 and P2).

Rory 2026-11-11: "world power is a type of global parameter, we could indicate power network id
from the pole, and then look at that grid as the global power stat. Pole types should be an input
so its configurable what poles are allowed and if multiple are allowed they can always be mixed."

FRICTION 11-11 (lab-session/fk-boot-w3): "cover power: all 25 spots taken" (a re-route took the
tile an inserter's pole stood on, and the build went on with NO_POWER; the sim's powerfix.py put in
the other pole kind by hand) and the stage's poles had to wire back to G1's standing poles
(trimpoles.py found that wire path by hand). No game: the grid read is a fixture terrain's.
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import avail, fkp, flow, power, supply, surface, terrain
from fkcore.catalog import Catalog
from fkcore.cover import (_Node, _groups, _keeps_power, _overlap, apply_cover, bridge,
                          cover_power)
from tests.test_terrain_flow import IRON, SCRIPT, SURFACE, fixture

CAT = Catalog.load()
SMALL, MEDIUM, BIG = "small-electric-pole", "medium-electric-pole", "big-electric-pole"


def _lay(size, *rows):
    lay = fkp.Layout("factory", "t", size=size)
    for key, name, x, y, d in rows:
        lay.add(fkp.Entity(key, name, x, y, d, {}))
    return lay


def boxed(free=()):
    """An inserter at tile 5,5 boxed in by belts on every other tile of 3..7 x 3..7 (the 25 tiles
    a small pole could power it from) but ``free``: FRICTION 11-11's "all 25 spots taken"."""
    rows = [("a/ins", "inserter", 5.5, 5.5, 0)]
    for x in range(3, 8):
        for y in range(3, 8):
            if (x, y) != (5, 5) and (x, y) not in free:
                rows.append((f"b/t{x}_{y}", "transport-belt", x + 0.5, y + 0.5, 0))
    return _lay((20, 20), *rows)


def grid_read(poles, gid=7, capacity=900000.0, used=None):
    return {"at": [poles[0][1], poles[0][2]], "id": gid, "pole": list(poles[0]),
            "poles": [list(p) for p in poles],
            "stats": {"tick": 99, "window": "1min",
                      "made_w": {"steam-engine": sum((used or {}).values())},
                      "used_w": dict(used or {}), "capacity_w": capacity,
                      "generators": {"steam-engine": 1} if capacity else {}, "accumulators": 0}}


class SurfaceLineTest(unittest.TestCase):
    def test_power_grid_parses_and_round_trips(self):
        sf = surface.loads("surface nauvis\npower grid 10.5,-3.5   # G1's pole\n")
        self.assertEqual(sf.power_grid, (10.5, -3.5))
        text = surface.properties(sf)
        self.assertIn("power grid 10.5,-3.5\n", text)
        self.assertEqual(surface.loads(text).power_grid, (10.5, -3.5))
        self.assertIsNone(surface.loads("surface nauvis\n").power_grid)
        self.assertNotIn("power", surface.properties(surface.loads("surface nauvis\n")))
        self.assertEqual(surface.loads("surface s\npower grid 4,6\n").power_grid, (4.0, 6.0))

    def test_malformed_lines_say_what_the_line_is(self):
        for bad in ("power grid", "power grid 1", "power net 1,2", "power grid a,b"):
            with self.assertRaises(surface.SurfaceError) as got:
                surface.loads(f"surface s\n{bad}\n")
            self.assertTrue("power grid" in str(got.exception)
                            or "expected x,y" in str(got.exception), str(got.exception))
        with self.assertRaises(surface.SurfaceError) as got:
            surface.loads("surface s\npower grid 1,2\npower grid 3,4\n")
        self.assertIn("one power grid line", str(got.exception))


class FrameTest(unittest.TestCase):
    def test_a_point_lands_where_compose_turns_it_from(self):
        from fkcore.compose import turn
        size = (12, 7)
        for rot in range(4):
            p = surface.Place("f", "f", 30, -20, 12, 12, rot)
            for x, y in ((0.5, 0.5), (11.5, 3.5), (4, 6), (6.5, 2)):
                tx, ty, _d = turn(x, y, None, rot, size)
                back = power.point_to_frame(tx + p.x, ty + p.y, p, size)
                self.assertAlmostEqual(back[0], x)
                self.assertAlmostEqual(back[1], y)

    def test_only_poles_in_reach_of_the_plot_are_roots(self):
        p = surface.Place("f", "f", 100, 100, 20, 10)
        g = grid_read([[MEDIUM, 95.5, 104.5], [MEDIUM, 90.5, 104.5], [MEDIUM, 125.5, 109.5],
                       ["no-such-pole", 101.5, 101.5], [BIG, 100.0, 80.0]])
        roots = power.grid_roots(g, p, (20, 10), CAT, (MEDIUM,))
        # 4.5 tiles west of the plot, and 5.5 east of it: in a medium's 9; 9.5 west: out; a big
        # pole 20 north, beyond the medium's reach; a kind the catalog does not know: left out
        self.assertEqual([(r.key, r.x, r.y) for r in roots],
                         [("grid#7/p0", -4.5, 4.5), ("grid#7/p2", 25.5, 9.5)])
        self.assertTrue(all(r.grid == 7 for r in roots))
        self.assertEqual(len(power.grid_roots(g, p, (20, 10), CAT, (BIG,))), 3)   # reach 32


class GridRootsCoverTest(unittest.TestCase):
    ROOT = power.Root("grid#7/p0", MEDIUM, -3.5, 2.5, 7)

    def test_the_cover_bridges_to_a_grid_pole_and_never_lays_it(self):
        lay = _lay((30, 8), ("a/m0", "assembling-machine-1", 20.5, 3.5, 0))
        poles, rep = cover_power(lay, CAT)
        self.assertEqual(len(poles), 1)                  # today: one pole, on its own
        poles, rep = cover_power(lay, CAT, roots=[self.ROOT])
        self.assertEqual(rep.components, 1)
        self.assertEqual(rep.grid, 1)
        self.assertNotIn("grid#7/p0", [p.key for p in poles])
        nodes = [_Node(-3.5, 2.5, 3.5, 9)] + [_Node(p.x, p.y, 3.5, 9) for p in poles]
        self.assertEqual(len(_groups(nodes)), 1)         # wired back to the grid
        self.assertGreater(len(poles), 1)
        self.assertIn("roots: 1 pole of the world grid, joined", rep.summary())
        new = apply_cover(lay, CAT, poles=poles)
        self.assertFalse([k for k in new.entities if k.startswith("grid#")])

    def test_a_grid_pole_powers_what_its_supply_reaches(self):
        lay = _lay((12, 8), ("a/m0", "assembling-machine-1", 1.5, 2.5, 0))
        poles, rep = cover_power(lay, CAT, roots=[power.Root("grid#7/p0", MEDIUM, -1.5, 2.5, 7)])
        self.assertEqual(poles, [])
        self.assertEqual(rep.covered, rep.total)

    def test_no_roots_is_todays_cover(self):
        lay = _lay((30, 8), ("a/m0", "assembling-machine-1", 20.5, 3.5, 0),
                   ("b/m0", "assembling-machine-1", 4.5, 3.5, 0))
        a, ra = cover_power(lay, CAT)
        b, rb = cover_power(lay, CAT, roots=(), more=())
        self.assertEqual([(p.key, p.name, p.x, p.y) for p in a],
                         [(p.key, p.name, p.x, p.y) for p in b])
        self.assertEqual(ra.summary(), rb.summary())
        self.assertNotIn("roots", ra.summary())

    def test_one_grid_id_is_one_wire_component_however_far_apart(self):
        far = [_Node(0.5, 0.5, 3.5, 9, key="g0", grid=7), _Node(200.5, 0.5, 3.5, 9, key="g1",
                                                               grid=7)]
        self.assertEqual(len(_groups(far)), 1)
        self.assertEqual(len(_groups([_Node(0.5, 0.5, 3.5, 9), _Node(200.5, 0.5, 3.5, 9)])), 2)

    def test_keeps_power_counts_grid_poles_as_roots(self):
        # Rory 11-11: the reducer never depowers anything. A grid root is a root: the bridge
        # between it and the pole that powers a/m0 stays built
        root = _Node(-3.5, 0.5, 3.5, 9, key="grid#7/p0", grid=7)
        a_pole = _Node(12.5, 0.5, 3.5, 9, spot=(12, 0))
        link = _Node(4.5, 0.5, 3.5, 9, spot=(4, 0))
        far = _Node(40.5, 0.5, 3.5, 9, spot=(40, 0))
        nodes, rects = [root, a_pole, link, far], [(11, 14, 1, 4)]
        self.assertTrue(_keeps_power(nodes, 1, rects, {id(far)}))
        self.assertFalse(_keeps_power(nodes, 1, rects, {id(link)}))
        # two grid poles far apart, one network: a pole by either one keeps it powered
        other = _Node(30.5, 0.5, 3.5, 9, key="grid#7/p1", grid=7)
        b_pole = _Node(36.5, 0.5, 3.5, 9, spot=(36, 0))
        nodes = [root, other, a_pole, link, b_pole]
        self.assertTrue(_keeps_power(nodes, 2, [(11, 14, 1, 4), (36, 39, 1, 4)], set()))

    def test_dnp_poles_wire_the_built_part_to_the_grid(self):
        lay = _lay((60, 8), ("a/m0", "assembling-machine-1", 12.5, 2.5, 0),
                   ("b/m0", "assembling-machine-1", 40.5, 2.5, 0))
        lay.entities["b/m0"].attrs["dnp"] = 1
        poles, rep = cover_power(lay, CAT, roots=[power.Root("grid#7/p0", MEDIUM, -3.5, 0.5, 7)])
        built = [p for p in poles if not p.attrs.get("dnp")]
        self.assertTrue(rep.dnp and built)
        nodes = [_Node(-3.5, 0.5, 3.5, 9, grid=7)] + [_Node(p.x, p.y, 3.5, 9) for p in built]
        self.assertEqual(len(_groups(nodes)), 1)
        self.assertTrue(all(p.x < 20 for p in built))


class KindLadderTest(unittest.TestCase):
    def test_all_25_spots_taken_gets_the_next_kind(self):
        # FRICTION 11-11: the small pole's 25 spots are all taken; a medium's reach is one ring
        # further out, where a tile is free
        _poles, rep = cover_power(boxed(), CAT, pole=SMALL)
        self.assertEqual([c.code for c in rep.checks], ["NO_POWER"])
        self.assertIn("all 25 spots a small-electric-pole could power it from are taken",
                      rep.checks[0].msg)
        poles, rep = cover_power(boxed(), CAT, pole=SMALL, more=(MEDIUM,))
        self.assertEqual(rep.checks, [])
        self.assertEqual([p.name for p in poles], [MEDIUM])
        self.assertIn("pole=small-electric-pole,medium-electric-pole", rep.summary())
        self.assertIn("(1 medium-electric-pole; ", rep.summary())

    def test_a_one_tile_gap_takes_a_small_pole_where_a_big_one_cannot_stand(self):
        lay = boxed(free={(7, 5)})
        _poles, rep = cover_power(lay, CAT, pole=BIG)
        self.assertEqual([c.code for c in rep.checks], ["NO_POWER"])
        poles, rep = cover_power(lay, CAT, pole=BIG, more=(SMALL,))
        self.assertEqual([(p.name, p.x, p.y) for p in poles], [(SMALL, 7.5, 5.5)])
        self.assertEqual(rep.covered, rep.total)
        self.assertEqual(rep.checks, [])

    def test_medium_then_small_where_a_mediums_reach_would_cross_a_domain(self):
        # a medium and a small pole are both 1x1, so a spot free for one is free for the other:
        # medium-then-small changes the answer only where the medium's wider supply is denied.
        # Every medium spot near the inserter reaches another domain's machine (deny), or is
        # taken; a small one at the ring's edge does not
        rows = [("a/ins", "inserter", 5.5, 5.5, 0)]
        rows += [(f"b/t{x}_{y}", "transport-belt", x + 0.5, y + 0.5, 0)
                 for x in range(4, 7) for y in range(4, 7) if (x, y) != (5, 5)]
        lay = _lay((12, 12), *rows)
        deny = [(0, 1, 5, 6), (10, 11, 5, 6), (5, 6, 0, 1), (5, 6, 10, 11)]
        _poles, rep = cover_power(lay, CAT, pole=MEDIUM, deny=deny)
        self.assertEqual([c.code for c in rep.checks], ["domain-overlap"])
        poles, rep = cover_power(lay, CAT, pole=MEDIUM, more=(SMALL,), deny=deny)
        self.assertEqual(rep.checks, [])
        self.assertEqual({p.name for p in poles}, {SMALL})
        for p in poles:                                   # the deny set holds on the ladder
            self.assertFalse(any(_overlap(r, p.x, p.y, 2.5) for r in deny))

    def test_a_component_the_first_kind_cannot_join_is_bridged_with_the_next(self):
        wall = {(x, y) for x in range(2, 10) for y in range(8)}
        lay = _lay((30, 8), ("src/p", MEDIUM, 0.5, 3.5, None),
                   ("a/m0", "assembling-machine-1", 20.5, 3.5, 0))
        _poles, rep = cover_power(lay, CAT, pole=SMALL, keep_out=wall)
        self.assertIn("power-split", [c.code for c in rep.checks])
        poles, rep = cover_power(lay, CAT, pole=SMALL, more=(MEDIUM,), keep_out=wall)
        self.assertEqual(rep.components, 1, rep.lines())
        self.assertIn(MEDIUM, {p.name for p in poles})
        self.assertIn(SMALL, {p.name for p in poles})
        self.assertRegex(rep.summary(), r"\(\d+ small-electric-pole, \d+ medium-electric-pole; ")

    def test_mixing_only_adds_poles_where_the_first_kind_left_a_gap(self):
        lay = _lay((40, 12), ("a/m0", "assembling-machine-1", 4.5, 4.5, 0),
                   ("b/m0", "assembling-machine-1", 14.5, 4.5, 0),
                   ("c/m0", "assembling-machine-1", 30.5, 8.5, 0))
        one, r1 = cover_power(lay, CAT)
        two, r2 = cover_power(lay, CAT, more=(SMALL,))
        self.assertEqual([(p.key, p.name, p.x, p.y) for p in one],
                         [(p.key, p.name, p.x, p.y) for p in two])
        self.assertIn("pole=medium-electric-pole: ", r1.summary())
        self.assertIn("pole=medium-electric-pole,small-electric-pole: ", r2.summary())

    def test_the_record_names_the_kinds_and_pinned_poles_of_an_allowed_kind_stay(self):
        poles, _rep = cover_power(boxed(), CAT, pole=SMALL, more=(MEDIUM,))
        new = apply_cover(boxed(), CAT, pole=SMALL, poles=poles, more=(MEDIUM,))
        self.assertEqual(new.covers["power"].params,
                         {"pole": SMALL, "poles": "small-electric-pole,medium-electric-pole"})
        again, rep = cover_power(boxed(), CAT, pole=SMALL, more=(MEDIUM,), pinned=poles)
        self.assertEqual([(p.key, p.name, p.x, p.y) for p in again],
                         [(p.key, p.name, p.x, p.y) for p in poles])
        self.assertEqual(rep.pinned, 1)
        one = apply_cover(boxed(), CAT, pole=MEDIUM)
        self.assertEqual(one.covers["power"].params, {"pole": MEDIUM})

    def test_bridge_power_takes_the_grid_as_a_source(self):
        ents = [fkp.Entity("grid#7/p0", MEDIUM, 0.5, 0.5, None, {}),
                fkp.Entity("s:f/power/p0", MEDIUM, 20.5, 0.5, None, {})]
        poles, lines = bridge(ents, CAT, (), MEDIUM, grid={"grid#7/p0"})
        self.assertEqual(len(poles), 2)                 # 20 tiles: two hops of at most 9
        self.assertIn("bridged the network of s:f/power/p0", lines[0])
        _poles, lines = bridge(ents, CAT, (), MEDIUM)
        self.assertIn("nothing to bridge to", lines[0])


class KindsInputTest(unittest.TestCase):
    def setUp(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    def tearDown(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    @staticmethod
    def sup(*rows):
        return supply.from_raw({"tick": 1, "force": "player", "surface": "nauvis",
                                "networks": 1, "entities": list(rows), "recipes": [],
                                "research": {}})

    @staticmethod
    def row(name, stock, enabled=True):
        return {"entity": name, "item": name, "stock": stock, "known": True, "enabled": enabled}

    def test_a_list_is_taken_in_order(self):
        self.assertEqual(power.parse_kinds("small-electric-pole, medium-electric-pole", CAT),
                         (SMALL, MEDIUM))
        self.assertEqual(power.parse_kinds(MEDIUM, CAT), (MEDIUM,))
        with self.assertRaises(ValueError) as got:
            power.parse_kinds("medium-electric-pole,mediun-electric-pole", CAT)
        self.assertIn("not an electric pole", str(got.exception))

    def test_any_is_the_avail_pick_then_the_other_buildable_kinds(self):
        self.assertEqual(power.parse_kinds("any", CAT), (MEDIUM,))      # nothing read: one kind
        avail.install(self.sup(self.row(MEDIUM, 93), self.row(SMALL, 60)))
        self.assertEqual(power.parse_kinds("any", CAT, need=10), (MEDIUM, SMALL))
        avail.install(self.sup(self.row(MEDIUM, 0, enabled=False), self.row(SMALL, 60)))
        self.assertEqual(power.parse_kinds("any", CAT, need=10), (SMALL,))
        avail.install(self.sup(self.row(MEDIUM, 93), self.row(SMALL, 60)))
        self.assertEqual(power.parse_kinds("small-electric-pole,any", CAT), (SMALL, MEDIUM))
        self.assertEqual(power.parse_kinds("big-electric-pole,any", CAT), (BIG, MEDIUM, SMALL))

    def test_kinds_text(self):
        self.assertEqual(power.kinds_text([MEDIUM] * 12 + [SMALL] * 2, (MEDIUM, SMALL)),
                         "12 medium-electric-pole, 2 small-electric-pole")


class GridReadTest(unittest.TestCase):
    RAW = {"at": [10.5, 4.5], "tick": 120, "pole": [MEDIUM, 10.5, 4.5], "id": 12,
           "poles": [[MEDIUM, 10.5, 4.5], [SMALL, 3.5, 4.5]],
           "stats": {"window": "one_minute", "tick": 120, "made": {"steam-engine": 9000},
                     "used": {"assembling-machine-2": 2500, "inserter": 500},
                     "max_production": 30000, "generators": {"steam-engine": 2}, "unknown": 0,
                     "accumulators": []}}

    def test_the_answer_becomes_the_record(self):
        g = power.normalise(self.RAW, (10.5, 4.5))
        self.assertEqual(g["id"], 12)
        self.assertEqual(g["poles"], [[SMALL, 3.5, 4.5], [MEDIUM, 10.5, 4.5]])
        self.assertEqual(g["stats"]["capacity_w"], 1800000.0)      # two engines, 900 kW each
        self.assertEqual(g["stats"]["used_w"], {"assembling-machine-2": 150000.0,
                                                "inserter": 30000.0})
        self.assertIn("the world grid #12 (2 poles; made 540 kW, used 180 kW over the last "
                      "minute; capacity 1.80 MW from 2 generators; read at tick 120)",
                      power.grid_text(g))

    def test_a_read_that_finds_nothing_says_why(self):
        g = power.normalise({"at": [1, 2], "why": "no electric pole of force player stands "
                                                  "within 1.5 tiles"}, (1, 2))
        self.assertEqual(g, {"at": [1.0, 2.0], "why": "no electric pole of force player stands "
                                                      "within 1.5 tiles"})
        from fkcore import link
        with mock.patch.object(link, "read_output", side_effect=link.LinkError("boom")):
            g = power.read_grid(object(), "nauvis", "player", (1, 2))
        self.assertIn("the read failed", g["why"])
        t = terrain.with_entities(fixture(), frozenset(), {"tick": 7, "area": [0, 0, 1, 1],
                                                           "count": 0, "names": {}, "grid": g})
        self.assertIsNone(terrain.grid(t))
        self.assertIn("power grid (the pole at 1,2, same read): none recorded, the read failed",
                      "\n".join(terrain.summary(t)))

    def test_the_lua_only_reads(self):
        lua = power.lua_grid("nauvis", "player", (10.5, 4.5), "t-grid")
        for bad in ("on_event", "on_nth_tick", "commands.add", "script.on_", "destroy",
                    "create_entity"):
            self.assertNotIn(bad, lua)
        self.assertIn("electric_network_id", lua)
        self.assertIn("get_max_energy_production", lua)
        self.assertIn("X, Y = 10.5, 4.5", lua)

    def test_read_entities_records_the_grid(self):
        from fkcore import link
        answers = {"snapshot": {"tick": 5, "things": []}, "roboports": [],
                   "power grid": self.RAW}
        with mock.patch.object(link, "read_output",
                               side_effect=lambda r, lua, tag, what, keep=True: answers[what]):
            _tiles, er = terrain.read_entities(object(), "nauvis", (0, 0, 10, 10), set(),
                                               grid_at=(10.5, 4.5))
        self.assertEqual(er["grid"]["id"], 12)
        with mock.patch.object(link, "read_output",
                               side_effect=lambda r, lua, tag, what, keep=True: answers[what]):
            _tiles, er = terrain.read_entities(object(), "nauvis", (0, 0, 10, 10), set())
        self.assertNotIn("grid", er)

    def test_the_file_keeps_it(self):
        g = power.normalise(self.RAW, (10.5, 4.5))
        t = terrain.with_entities(fixture(), frozenset(), {"tick": 7, "area": [0, 0, 1, 1],
                                                           "count": 0, "names": {}, "grid": g})
        d = tempfile.mkdtemp(prefix="fkgrid-")
        try:
            path = os.path.join(d, "map.terrain.json")
            terrain.save(t, path)
            back = terrain.load(path)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(terrain.grid(back), g)
        self.assertIn("power grid (the pole at 10.5,4.5, same read): the world grid #12",
                      "\n".join(terrain.summary(back)))


class GridFlowTest(unittest.TestCase):
    """The flow on test_terrain_flow's fixture (plot iron at 0,0 90x70, no generator), with a
    world grid in the terrain's entity read."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkgridflow-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self, g, script=SCRIPT):
        t = fixture()
        read = {"tick": 7, "area": list(t.area), "count": 0, "names": {}}
        if g is not None:
            read["grid"] = g
        t = terrain.with_entities(t, frozenset(), read)
        terrain.save(t, os.path.join(self.dir, "map.terrain.json"))
        for name, text in (("t.surface", SURFACE + "power grid -3.5,10.5\n"),
                           ("t.build.fkb", script), ("iron.fk", IRON)):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        _code, ctx = flow.run(os.path.join(self.dir, "t.build.fkb"), cat=CAT,
                              echo=lambda _l: None)
        return ctx

    def read(self, name):
        with open(os.path.join(self.dir, "out", name), encoding="utf-8") as fh:
            return fh.read()

    def test_a_plot_near_the_grid_is_on_it(self):
        ctx = self.build(grid_read([[MEDIUM, -3.5, 10.5], [MEDIUM, -3.5, 1.5]],
                                   capacity=1.8e6))
        self.assertNotIn(("floorplan", "NO_POWER"), {(s, c.code) for s, c in ctx.checks})
        cover_txt = self.read("cover_power.txt")
        self.assertIn("iron: the world grid #7 (2 poles;", cover_txt)
        self.assertIn("2 of its poles in reach of the plot, the cover's roots", cover_txt)
        self.assertIn("roots: 2 poles of the world grid, joined", cover_txt)
        fp = self.read("floorplan.txt")
        self.assertIn("iron: ", fp)
        self.assertRegex(fp, r"iron: \d+ poles, on the world grid #7 \(2 poles; ")
        self.assertIn("read-terrain", self.read("read_terrain.txt") + "read-terrain")
        self.assertIn("power grid (the pole at -3.5,10.5, same read): the world grid #7",
                      self.read("read_terrain.txt"))
        lay = ctx.layouts["iron"]
        self.assertFalse([k for k in lay.entities if k.startswith("grid#")])
        self.assertFalse([e for e in lay.entities.values() if (e.x, e.y) == (-3.5, 10.5)])
        # power-short: 1.8 MW rated, nothing used: the iron row fits, said in one line
        self.assertIn("power-short (offline, nominal)", fp)
        self.assertRegex(fp, r"iron: draws \d+ kW at full load, against 1\.80 MW spare")
        self.assertNotIn("power-short", {c.code for _s, c in ctx.checks})

    def test_a_plot_far_from_the_grid_names_it_in_no_power(self):
        ctx = self.build(grid_read([[MEDIUM, 300.5, 300.5]]))
        bad = [c for s, c in ctx.checks if s == "floorplan" and c.code == "NO_POWER"]
        self.assertEqual(len(bad), 1, [str(c) for _s, c in ctx.checks])
        self.assertIn("its poles reach neither a generator nor the world grid #7", bad[0].msg)
        self.assertIn("0 of its poles in reach of the plot", self.read("cover_power.txt"))
        self.assertRegex(self.read("floorplan.txt"),
                         r"iron: \d+ poles, NOT on the world grid #7 or a grid with generation")

    def test_power_short_when_the_grid_has_no_room(self):
        ctx = self.build(grid_read([[MEDIUM, -3.5, 10.5]], capacity=900000.0,
                                   used={"assembling-machine-2": 880000.0}))
        short = [c for _s, c in ctx.checks if c.code == "power-short"]
        self.assertEqual(len(short), 1, [str(c) for _s, c in ctx.checks])
        self.assertIn("the world grid #7 has 20 kW spare (900 kW rated less 880 kW used", short[0].msg)
        self.assertIn("nauvis iron", short[0].where)

    def test_capacity_unknown_is_said_not_weighed(self):
        ctx = self.build(grid_read([[MEDIUM, -3.5, 10.5]], capacity=None))
        self.assertIn("the grid's capacity is unknown, so it is not weighed",
                      self.read("floorplan.txt"))
        self.assertNotIn("power-short", {c.code for _s, c in ctx.checks})

    def test_the_step_takes_a_list_and_reports_per_kind(self):
        script = SCRIPT.replace("--pole medium-electric-pole",
                                "--pole small-electric-pole,medium-electric-pole")
        ctx = self.build(None, script)
        line = [ln for ln in self.read("cover_power.txt").splitlines()
                if "cover power power pole=" in ln][0]
        self.assertIn("pole=small-electric-pole,medium-electric-pole: ", line)
        self.assertRegex(line, r"\(\d+ small-electric-pole[;,]")
        names = {e.name for e in ctx.layouts["iron"].entities.values()
                 if CAT.kind(e.name) == "electric-pole"}
        self.assertIn(SMALL, names)
        self.assertLessEqual(names, {SMALL, MEDIUM})
        bad = SCRIPT.replace("--pole medium-electric-pole", "--pole medium-electric-pole,nope")
        with self.assertRaises(flow.FlowError) as got:
            self.build(None, bad)
        self.assertIn("--pole nope: not an electric pole", str(got.exception))

    def test_without_a_grid_read_floorplan_is_as_before(self):
        ctx = self.build(None)
        bad = [c for s, c in ctx.checks if s == "floorplan" and c.code == "NO_POWER"]
        self.assertEqual([c.msg for c in bad], ["its grid reaches no generator (bridge it: "
                                                "floorplan --bridge-power)"])
        self.assertNotIn("world grid", self.read("floorplan.txt"))
        self.assertNotIn("world grid", self.read("cover_power.txt"))


if __name__ == "__main__":
    unittest.main()
