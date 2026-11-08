"""SmelterArray (2.0): Rory's smelter stack as a template (games/v2-bench/smelter-stack-ghosts.json),
fed by side-loading: ore and coal on the two lanes of each column's belt. It tiles to any count,
n=auto included, and the routed rates hold the benchmark's numbers (CORE-V2.md "The benchmark")."""
import json
import os
import unittest

from fkcore import connect, expand, fkp, fragments, lang, route, routed, size
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate

CAT = Catalog.load()
BENCH = os.path.join(os.path.dirname(__file__), "..", "games", "v2-bench")


def factory(n, drills=30, extra="", sinks=7):
    boxes = "".join(f"box{i} = Chest<provider> @({4 + 3 * i}, 96)\n" for i in range(sinks))
    return f"""
ore   = MinerRow<n={drills}, resource=iron-ore> @({2 + drills * 3 // 2}, 7, rot 2)
coal  = MinerRow<n=4, resource=coal>          @(62, 7, rot 2)
smelt = SmelterArray<n={n}, recipe=iron-plate{extra}> @(4, 14)
{boxes}net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> {', '.join(f'box{i}' for i in range(sinks))}
"""


def built(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, notes = expand.expand_factory(flat, CAT)
    assert notes == [], notes
    r = route.route_layout(flat, lay, CAT)
    return flat, r, routed.solve(flat, r.layout, CAT)


class GeometryTest(unittest.TestCase):
    def test_rorys_two_units(self):
        # his ghost at 2 furnaces per column, pasted twice (x 86..107): entity for entity, but
        # for the westmost unit's dead-end coal pass-through and the coal's port at the east end
        ents, roles, size_ = fragments.smelter_array(8, "iron-plate", [["iron-ore"], ["coal"]],
                                                     [["iron-plate"]], fuel="coal", units=2)
        ug = {"input": "in", "output": "out"}
        with open(os.path.join(BENCH, "smelter-stack-ghosts.json"), encoding="utf-8") as fh:
            ghost = {(g["n"], float(g["x"]), float(g["y"]), g["d"], ug.get(g.get("ug")))
                     for g in json.load(fh)["ghosts"] if 86 <= g["x"] < 108}
        mine = {(e.name, float(e.x) + 86, float(e.y) + 108, e.dir or 0, e.attrs.get("ug"))
                for e in ents}
        self.assertEqual(mine - ghost, {("underground-belt", 108.5, 113.5, 12, "in")})
        self.assertEqual(ghost - mine, {("underground-belt", 87.5, 113.5, 12, "in"),
                                        ("underground-belt", 88.5, 113.5, 12, "out"),
                                        ("underground-belt", 91.5, 113.5, 12, "in")})
        self.assertEqual(size_, (23, 10))
        self.assertEqual(roles["in1"].attach, [(3.5, 9.5, 0), (14.5, 9.5, 0)])
        self.assertEqual(roles["in2"].attach, [(22.5, 5.5, 12)])
        self.assertEqual(roles["out"].attach, [(5.5, 9.5, 8), (16.5, 9.5, 8)])

    def test_the_feed_belts_carry_both_nets(self):
        ents, _roles, _size = fragments.smelter_array(4, "iron-plate", [["iron-ore"], ["coal"]],
                                                      [["iron-plate"]], fuel="coal")
        role = {e.local: e.role for e in ents}
        self.assertEqual(role["feed0w0"], "in1|in2")      # west: ore on the left lane
        self.assertEqual(role["feed0e0"], "in2|in1")      # east: coal on the left lane
        self.assertEqual(role["f0"], "in1|in2")

    def test_any_count(self):
        self.assertEqual(fragments.array_shape(48, 24), (1, [48]))
        self.assertEqual(fragments.array_shape(49, 24), (2, [25, 24]))
        self.assertEqual(fragments.array_shape(7, 24, units=3), (3, [3, 2, 2]))
        for n in (1, 2, 3, 13, 49, 100):
            ents, _roles, (w, h) = fragments.smelter_array(
                n, "iron-plate", [["iron-ore"], ["coal"]], [["iron-plate"]], fuel="coal")
            self.assertEqual(sum(1 for e in ents if e.name == "stone-furnace"), n)
            tiles = [t for e in ents for t in CAT.tiles(e.name, e.x, e.y, e.dir or 0)]
            self.assertEqual(len(tiles), len(set(tiles)), n)
            self.assertTrue(all(0 <= x < w and 0 <= y < h for x, y in tiles), n)

    def test_steel_furnaces_take_12_a_column(self):
        f = lang.parse("o = MinerRow<n=1, resource=iron-ore> @(0, 0)\n"
                       "c = MinerRow<n=1, resource=coal> @(10, 0)\n"
                       "s = SmelterArray<n=30, recipe=iron-plate, machine=steel-furnace> @(0, 10)\n"
                       "net a: o -> s\nnet b: c -> s\n", "t.fk")
        flat = elaborate(f, {}, CAT, "t")
        frag, binding = expand.fragment_of(flat, "s", CAT)
        self.assertEqual(frag.params["_per"], 12)
        self.assertEqual(len(frag.roles["in1"].attach), 2)       # 30 furnaces: two units
        self.assertEqual((binding["in1"], binding["in2"]), ("a", "b"))

    def test_what_it_takes(self):
        def elab(params, nets="net a: o -> s\nnet b: c -> s\n"):
            f = lang.parse("o = MinerRow<n=1, resource=iron-ore> @(0, 0)\n"
                           "c = MinerRow<n=1, resource=coal> @(10, 0)\n"
                           f"s = SmelterArray<{params}> @(0, 10)\n" + nets, "t.fk")
            return elaborate(f, {}, CAT, "t")
        for params, msg in (("n=4, recipe=iron-plate, machine=electric-furnace", "2x2 burners"),
                            ("n=2, recipe=iron-plate, units=3", "more units than")):
            with self.assertRaises(ElabError) as cm:
                elab(params)
            self.assertIn(msg, str(cm.exception))
        flat = elab("n=4, recipe=iron-plate", "net a: o -> s\nnet b: c -> s\nlanes a | b\n")
        with self.assertRaises(fragments.FragmentError) as cm:
            expand.fragment_of(flat, "s", CAT)
        self.assertIn("two nets that share no belt", str(cm.exception))


class RatesTest(unittest.TestCase):
    """CORE-V2.md "The benchmark: Rory's smelter stack", on the template as routed."""

    @classmethod
    def setUpClass(cls):
        cls.flat, cls.r, cls.rr = built(factory(48))

    def test_routed_and_connected(self):
        self.assertEqual(self.r.failed, {})
        self.assertEqual(fkp.invariants(self.r.layout, CAT, nets=self.flat.nets), [])
        rep = connect.connect(self.r.layout, CAT, connect.endpoints(self.flat))
        self.assertEqual(rep.checks, [])

    def test_48_furnaces_make_a_full_belt(self):
        rr = self.rr
        plates = sum(rr.res.delivered.get((k, ""), {}).get("iron-plate", 0.0)
                     for k in self.flat.machines if k.startswith("box"))
        self.assertAlmostEqual(plates, 15.0, places=4)
        self.assertTrue(all(abs(rr.util(k) - 1) < 1e-6 for k in self.flat.insts["smelt"].machines))
        # every side-load joint runs at exactly its lane: ore on the west belt's left lane
        west = ("smelt/feed0m2", "L")
        self.assertAlmostEqual(rr.res.load(west), 1.0, places=6)
        self.assertAlmostEqual(rr.ratio(west), 1.0, places=6)
        self.assertEqual(set(rr.res.flow[west]), {"iron-ore"})
        self.assertEqual(set(rr.res.flow[("smelt/feed0m2", "R")]), {"coal"})
        _lines, checks = routed.report(rr)
        self.assertEqual([c for c in checks if c.code in ("too-thin", "WRONG-LANE")], [])

    def test_a_25th_per_column_starves(self):
        # 32 drills (16/s) for 50 furnaces in one unit: a column's ore lane feeds 24, and its
        # plate lane takes 24's plates. The two furnaces short settle as the top one of each
        # column starved of ore and a bottom one blocked by its plate lane, half each
        flat, _r, rr = built(factory(50, drills=32, extra=", units=1"))
        us = [rr.util(k) for k in flat.insts["smelt"].machines]
        self.assertAlmostEqual(sum(us), 48.0, places=4)
        self.assertEqual(sum(1 for u in us if u < 1 - 1e-3), 4)
        lines, checks = routed.report(rr)
        self.assertIn("2 of 50 starved of iron-ore; 2 of 50 blocked (output backs up)",
                      next(x for x in lines if x.strip().startswith("smelt ")))
        where = {(c.where, c.msg.split(": ", 1)[0]) for c in checks if c.code == "too-thin"}
        self.assertIn(("net ore_", "7.81/s required where its yellow splitters (a lane a side) "
                                   "carry 7.50/s (ratio 1.04)"), where)
        self.assertIn(("net plates", "7.81/s required where its yellow lanes carry 7.50/s "
                                     "(ratio 1.04)"), where)


class ExampleTest(unittest.TestCase):
    def test_smelter_array_as_examples_md_says(self):
        from fkcore.elaborate import elaborate_file
        path = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples",
                            "smelter-array.fk")
        flat = elaborate_file(path, CAT)
        lay, notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual((notes, r.failed), ([], {}))
        self.assertEqual(connect.connect(r.layout, CAT, connect.endpoints(flat)).checks, [])
        rr = routed.solve(flat, r.layout, CAT)
        self.assertTrue(all(abs(rr.util(k) - 1) < 1e-6 for k in flat.insts["smelt"].machines))
        lines, checks = routed.report(rr)
        self.assertIn("~plates/i", next(x for x in lines if x.strip().startswith("plates ")))
        self.assertEqual([c for c in checks if c.code in ("too-thin", "WRONG-LANE")], [])


class AutoTest(unittest.TestCase):
    def test_n_auto_sizes_to_an_assert(self):
        text = factory("auto", sinks=1).replace(
            "net plates", "assert smelt.rate >= 10/s\nnet plates")
        sz = size.size({"t": lambda sizes: elaborate(*_parsed(text), CAT, "t", None, sizes)},
                       None)
        (row,) = [r for r in sz.rows if r.path == "smelt"]
        self.assertEqual(row.n, 32)                        # 32 x 0.3125 = 10 plates/s
        flat = sz.flats["t"]
        frag, _binding = expand.fragment_of(flat, "smelt", CAT)
        self.assertEqual(sum(1 for e in frag.entities if e.name == "stone-furnace"), 32)


def _parsed(text):
    f = lang.parse(text, "t.fk")
    return f, dict(f.modules)


if __name__ == "__main__":
    unittest.main()
