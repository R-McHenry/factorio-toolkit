"""Two nets that share a belt (2.0, Rory 2026-10-21: a net is one lane): ``lanes A | B`` in the
source, ``net=A|B`` in the record, the judge, the router's join and the routed rates per lane."""
import contextlib
import copy
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import __main__ as cli
from fkcore import compose, connect, expand, fkp, flow, lang, lanes, merge, route, routed, sense
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate
from tests import test_sense
from tests.test_fkp import MINI

CAT = Catalog.load()

SMELT = """
ore   = MinerRow<n=2, resource=iron-ore>   @(14, 0, rot 2)
coal  = MinerRow<n=1, resource=coal>       @(24, 0, rot 2)
smelt = SmelterRow<n=4, recipe=iron-plate> @(6, 12)
pipes = AsmRow<n=1, recipe=pipe>           @(6, 24)
box   = Chest<provider>                    @(2, 30)
net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> pipes
net out:    pipes -> box
lanes ore_ | fuel
"""
PAIR = "ore_|fuel"


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def routed_layout(text=SMELT):
    flat = flat_of(text)
    lay, notes = expand.expand_factory(flat, CAT)
    r = route.route_layout(flat, lay, CAT)
    return flat, r


def L(rows):
    return fkp.loads("fkp 1 factory t\n" + "\n".join(r.strip() for r in rows.strip().splitlines()))


class SourceTest(unittest.TestCase):
    def test_lanes_parses(self):
        f = lang.parse("net a: x -> y\nnet b: x -> y\nlanes a | b\n", "t.fk")
        (ln,) = f.body.lanes
        self.assertEqual((ln.left, ln.right, ln.line), ("a", "b", 3))

    def test_lanes_is_still_an_instance_name(self):
        f = lang.parse("lanes = Chest<provider> @(0, 0)\n", "t.fk")
        self.assertEqual(f.body.insts[0].name, "lanes")

    def test_lanes_needs_two_nets(self):
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse("lanes a b\n", "t.fk")
        self.assertIn("lanes LEFT | RIGHT", str(cm.exception))
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse("lanes a | a\n", "t.fk")
        self.assertIn("a net is one lane", str(cm.exception))

    def test_the_pair(self):
        flat = flat_of(SMELT)
        self.assertEqual(flat.pairs, {PAIR: ("ore_", "fuel")})
        self.assertEqual(flat.lane_of, {"ore_": PAIR, "fuel": PAIR})

    def test_two_single_nets_on_one_belt_draw_no_clog(self):
        flat = flat_of(SMELT)
        self.assertFalse(flat.nets["ore_"].sushi or flat.nets["fuel"].sushi)
        self.assertEqual([c for c in flat.checks if c.code in ("CLOG", "SUSHI_SINK")], [])

    def test_malformed_pairs(self):
        for extra, msg in (("lanes plates | coal_\n", "no net coal_"),
                           ("net more: ore -> smelt\nlanes more | fuel\n", "already shares a belt")):
            with self.assertRaises(ElabError) as cm:
                flat_of(SMELT + extra)
            self.assertIn(msg, str(cm.exception))

    def test_a_fluid_net_has_no_lanes(self):
        with self.assertRaises(ElabError) as cm:
            flat_of("""
                w = OffshorePump<rate=1200/s> @(0, 0)
                b = Boiler<fuel=coal>         @(4, 0)
                c = MinerRow<n=1, resource=coal> @(10, 0)
                net water: w -> b
                net fuel:  c -> b
                lanes water | fuel
            """)
        self.assertIn("pipes have no lanes", str(cm.exception))


class RecordTest(unittest.TestCase):
    def test_notation(self):
        self.assertEqual(fkp.net_names("ore|fuel"), ["ore", "fuel"])
        self.assertEqual(fkp.net_names("ore+fuel|"), ["ore", "fuel"])
        self.assertEqual(fkp.net_lanes("ore|fuel"), {"L": ["ore"], "R": ["fuel"]})
        self.assertEqual(fkp.net_lanes("|fuel"), {"L": [], "R": ["fuel"]})
        self.assertIsNone(fkp.net_lanes("ore"))
        self.assertEqual(fkp.hand_net("ore|fuel"), "ore+fuel")
        self.assertEqual(fkp.map_nets("a/ore|a/fuel", lambda n: "m/" + n), "m/a/ore|m/a/fuel")

    def test_invariants(self):
        def problems(text, nets=("a", "b")):
            return "\n".join(fkp.invariants(L(text), CAT, nets=nets))
        self.assertEqual(problems("e ~a|b/b0 transport-belt 0.5,0.5 E net=a|b"), "")
        self.assertEqual(problems("e ~a|b/i0 inserter 0.5,0.5 E net=a+b"), "")
        self.assertIn("two lanes, not 3", problems("e ~a|b/b0 transport-belt 0.5,0.5 E net=a|b|a"))
        self.assertIn("has no lanes (a|b): its nets are written a+b",
                      problems("e ~a|b/i0 inserter 0.5,0.5 E net=a|b"))
        self.assertIn("owner ~a|c is not a net",
                      problems("e ~a|c/b0 transport-belt 0.5,0.5 E net=a|b"))

    def test_the_row_belt_of_a_pair(self):
        flat = flat_of(SMELT)
        lay, _notes = expand.expand_factory(flat, CAT)
        self.assertEqual(fkp.invariants(lay, CAT, nets=flat.nets), [])
        self.assertEqual({e.net for k, e in lay.entities.items() if k.startswith("smelt/in1b")},
                         {PAIR})
        self.assertEqual({e.net for k, e in lay.entities.items() if k.startswith("smelt/f")},
                         {"ore_+fuel"})
        self.assertFalse(any(k.startswith("smelt/in2") for k in lay.entities))   # one belt


class JudgeTest(unittest.TestCase):
    def test_a_side_load_onto_its_pair_is_no_leak(self):
        rep = connect.connect(L("""
            e x/b0 transport-belt 1.5,1.5 E net=a|b
            e x/b1 transport-belt 2.5,1.5 E net=a|b
            e y/s0 transport-belt 2.5,2.5 N net=a"""), CAT)
        self.assertEqual(rep.leaks, [])

    def test_a_pair_into_one_of_its_nets_leaks_the_other(self):
        rep = connect.connect(L("""
            e x/b0 transport-belt 0.5,0.5 E net=a|b
            e y/b0 transport-belt 1.5,0.5 E net=a"""), CAT)
        self.assertEqual([str(c) for c in rep.checks if c.code == "LEAK"],
                         ["LEAK        net b: x/b0 feeds y/b0 (net a)"])


class RouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat, cls.r = routed_layout()
        cls.rr = routed.solve(cls.flat, cls.r.layout, CAT)

    def test_one_job_and_a_join(self):
        js = route.jobs(self.flat, expand.expand_factory(self.flat, CAT)[0], CAT)
        self.assertNotIn("ore_", js)
        self.assertNotIn("fuel", js)
        self.assertEqual(len(js[PAIR].parts), 3)
        self.assertEqual(self.r.failed, {})
        line = next(x for x in self.r.lines if x.startswith(f"routed    {PAIR}"))
        self.assertIn("(ore_ on the left lane, fuel on the right)", line)

    def test_connected_no_leak(self):
        self.assertEqual(fkp.invariants(self.r.layout, CAT, nets=self.flat.nets), [])
        rep = connect.connect(self.r.layout, CAT, connect.endpoints(self.flat))
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {n: "connected" for n in self.flat.nets})
        self.assertEqual(rep.checks, [])

    def test_the_parts_and_their_nets(self):
        ents = {k: e for k, e in self.r.layout.entities.items() if k.startswith(f"~{PAIR}/")}
        self.assertEqual({e.net for k, e in ents.items() if k.split("/")[-1].startswith("l")},
                         {"ore_"})
        self.assertEqual({e.net for k, e in ents.items() if k.split("/")[-1].startswith("r")},
                         {"fuel"})
        both = [e for k, e in ents.items() if k.split("/")[-1][0] in "bsu"]
        self.assertTrue(both)
        self.assertEqual({e.net for e in both}, {PAIR})

    def test_each_net_keeps_its_lane(self):
        res = self.rr.res
        side = [e for e in self.rr.lg.edges() if e.via == "side"]
        self.assertEqual(len(side), 4)                     # both lanes of each net, onto one
        for nid, nets in self.rr.net_of.items():
            items = set(res.flow.get(nid, {}))
            if nets == ("ore_",):
                self.assertLessEqual(items, {"iron-ore"}, nid)
            elif nets == ("fuel",):
                self.assertLessEqual(items, {"coal"}, nid)
        lanes_ = {nid[1] for nid, nets in self.rr.net_of.items()
                  if nid[0].startswith(f"~{PAIR}/b") and nets == ("ore_",)}
        self.assertEqual(lanes_, {"L"})
        self.assertGreater(sum(res.flow.get(("smelt/in1b0", "L"), {}).values()), 0.9)
        self.assertEqual(set(res.flow.get(("smelt/in1b0", "R"), {})), {"coal"})

    def test_routed_report_per_lane(self):
        lines, checks = routed.report(self.rr)
        ore = next(x for x in lines if x.strip().startswith("ore_ "))
        self.assertRegex(ore, r"\.L \(yellow lanes\)")
        self.assertEqual([c for c in checks if c.code == "LANE"], [])

    def test_swapped_lanes_draw_lane(self):
        lay = self.r.layout
        swapped = fkp.Layout(lay.level, lay.name, lay.size, dict(lay.insts), dict(lay.covers),
                             dict(lay.plots), dict(lay.claims), dict(lay.marks),
                             dict(lay.entities))
        for k, e in lay.entities.items():
            if e.net == PAIR:
                swapped.entities[k] = fkp.Entity(e.key, e.name, e.x, e.y, e.dir,
                                                 dict(e.attrs, net="fuel|ore_"))
        lines = [str(c) for c in routed.lane_checks(routed.solve(self.flat, swapped, CAT))]
        self.assertTrue(any(x.startswith("LANE        net ore_: its iron-ore reaches the left "
                                         "lane of") and "which the layout gives net fuel" in x
                            for x in lines), lines)

    def test_a_rebuild_keeps_the_pair(self):
        # route patching (merged before lanes, 2026-10-22): the committed routes go to the router
        # as ``patch=``, which keeps, patches or routes each again
        new, _notes = expand.expand_factory(self.flat, CAT)
        pinned, again = flow._pinned_routes(self.flat, new, self.r.layout, CAT)
        self.assertIn(PAIR, pinned)
        self.assertEqual(again, {})
        r2 = route.route_layout(self.flat, new, CAT, patch=pinned)
        self.assertIn(PAIR, r2.kept)
        self.assertEqual(r2.again, {})


class ClosedSideTest(unittest.TestCase):
    def test_items_on_the_closed_side_of_an_underground(self):
        # a belt east into the side of an underground entrance heading south: its left (north)
        # lane is on the entrance's open side (upstream, north); its right lane stops there
        flat = flat_of("""
            a = Assembler<recipe=iron-gear-wheel> @(0, 0)
            b = Assembler<recipe=transport-belt>  @(1, 9)
            net p: a -> b
        """)
        lay = L("""
            e a/m0 assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
            e r/o0 fast-inserter 1.5,3.5 N net=p
            e r/b0 transport-belt 1.5,4.5 E net=p
            e r/u0 underground-belt 2.5,4.5 S net=p ug=in
            e r/u1 underground-belt 2.5,7.5 S net=p ug=out
            e r/b1 transport-belt 2.5,8.5 S net=p
            e r/f0 fast-inserter 2.5,9.5 N net=p
            e b/m0 assembling-machine-1 2.5,11.5 recipe=transport-belt""")
        lay.insts = {"a": fkp.Inst("a", "Assembler", {}, 0, 0, 0, ""),
                     "b": fkp.Inst("b", "Assembler", {}, 1, 9, 0, "")}
        lg = lanes.build(lay, CAT)
        self.assertEqual(lg.closed, [(("r/b0", "R"), "r/u0")])
        lines = [str(c) for c in routed.lane_checks(routed.solve(flat, lay, CAT))]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("iron-gear-wheel on the right lane of r/b0 reach underground r/u0 from its "
                      "closed side and stop there", lines[0])


class ExampleTest(unittest.TestCase):
    def test_shared_belt_as_examples_md_says(self):
        from fkcore.elaborate import elaborate_file
        path = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples",
                            "shared-belt.fk")
        flat = elaborate_file(path, CAT)
        self.assertEqual([c for c in flat.checks if c.code == "CLOG"], [])
        lay, notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual((notes, r.failed), ([], {}))
        self.assertIn("join 8,8 E (ore_ on the left lane, fuel on the right)",
                      next(x for x in r.lines if x.startswith(f"routed    {PAIR}")))
        self.assertEqual(connect.connect(r.layout, CAT, connect.endpoints(flat)).checks, [])
        rr = routed.solve(flat, r.layout, CAT)
        self.assertEqual([round(rr.util(k), 3) for k in flat.insts["smelt"].machines],
                         [1.0] * 6 + [0.4, 0.0])


class ModuleTest(unittest.TestCase):
    def test_a_pair_in_a_module_and_merged(self):
        body = "\n".join("  " + x for x in SMELT.strip().splitlines())
        flat = flat_of(f"module South {{\n{body}\n}}\nsouth = South @(0, 0)\n")
        self.assertEqual(flat.pairs, {"south/ore_|south/fuel": ("south/ore_", "south/fuel")})
        # fk merge renames a merged factory's carriers the same way
        e = merge._rename(fkp.Entity("~ore_|fuel/b0", "transport-belt", 1.5, 0.5, 4,
                                     {"net": "ore_|fuel"}), "south", {}, 0, 0)
        self.assertEqual((e.key, e.net), ("~south/ore_|south/fuel/b0", "south/ore_|south/fuel"))
        self.assertEqual(e.owner[1:], next(iter(flat.pairs)))


SMELT2 = "smelt2 = SmelterRow<n=2, recipe=iron-plate> @(22, 12)\npipes = AsmRow"


def committed(r):
    out = {}
    for e in r.layout.entities.values():
        if e.owner.startswith("~"):
            out.setdefault(e.owner[1:], []).append(e)
    return out


class PatchPairTest(unittest.TestCase):
    """2.0.2: a lane pair whose ends were only added or dropped is patched like one net (route
    patching, Rory 2026-10-21: "Pin what stands and make patch changes rather than regenerating
    the base"), each new end on its own net's lane; 2.0.1 routed a changed pair again whole."""

    @classmethod
    def setUpClass(cls):
        cls.flat, cls.r = routed_layout()
        cls.old = committed(cls.r)

    def patched(self, text, old=None):
        flat = flat_of(text)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT, patch=old or self.old)
        self.assertEqual(fkp.invariants(r.layout, CAT, nets=flat.nets), [])
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {n: "connected" for n in flat.nets})
        self.assertEqual(rep.checks, [])                               # no LEAK
        self.assertEqual(routed.lane_checks(routed.solve(flat, r.layout, CAT)), [])  # no LANE
        return r

    def new_carriers(self, r):
        was = {(e.name, e.x, e.y, e.dir, e.net) for e in self.old[PAIR]}
        return [e for k, e in r.layout.entities.items() if k.startswith(f"~{PAIR}/")
                and (e.name, e.x, e.y, e.dir, e.net) not in was]

    def test_a_consumer_of_the_pair_branches_off_both_lanes(self):
        r = self.patched(SMELT.replace("pipes = AsmRow", SMELT2)
                         .replace("ore -> smelt", "ore -> smelt, smelt2")
                         .replace("coal -> smelt", "coal -> smelt, smelt2"))
        self.assertEqual((r.routed, r.again), ([], {}))
        # 28 of the pair's 29 carriers stand; the 29th, a straight belt of both lanes, became the
        # splitter, and the branch to smelt2 carries both lanes (a splitter keeps each on its own)
        self.assertRegex(r.patched[PAIR], r"^2 -> 2, smelt2\.in1: a splitter in place of "
                                          r"~ore_\|fuel/b\d+, \d+ belts; 28 of 29 carriers kept$")
        self.assertEqual({e.net for e in self.new_carriers(r)}, {PAIR})

    def test_a_driver_of_one_net_joins_its_own_lane(self):
        r = self.patched(SMELT.replace("pipes = AsmRow", "ore2  = MinerRow<n=1, resource=iron-ore>"
                                                         "   @(32, 0, rot 2)\npipes = AsmRow")
                         .replace("net ore_:   ore -> smelt", "net ore_:   ore, ore2 -> smelt"))
        # ore_ is the left lane: its new miner side-loads onto the pair's belt from the left
        self.assertRegex(r.patched[PAIR], r"^3 -> 1, ore2\.out: \d+ belts.*, side-loaded onto the "
                                          r"left lane of ~ore_\|fuel/b\d+; 29 of 29 carriers kept$")
        new = self.new_carriers(r)
        self.assertEqual({e.net for e in new}, {"ore_"})
        self.assertTrue(all(e.key.split("/")[-1].startswith("l") for e in new))
        r = self.patched(SMELT.replace("pipes = AsmRow", "coal2 = MinerRow<n=1, resource=coal>"
                                                         "       @(32, 0, rot 2)\npipes = AsmRow")
                         .replace("net fuel:   coal -> smelt", "net fuel:   coal, coal2 -> smelt"))
        self.assertIn("29 of 29 carriers kept", r.patched[PAIR])
        self.assertEqual({e.net for e in self.new_carriers(r)}, {"fuel"})

    def test_a_dropped_consumer_takes_its_branch_up(self):
        both = (SMELT.replace("pipes = AsmRow", SMELT2)
                .replace("ore -> smelt", "ore -> smelt, smelt2")
                .replace("coal -> smelt", "coal -> smelt, smelt2"))
        _flat, r = routed_layout(both)
        r = self.patched(SMELT.replace("pipes = AsmRow", SMELT2), committed(r))
        self.assertRegex(r.patched[PAIR], r"^2 -> 1, \d+ carriers taken up \(no end of the net "
                                          r"needs them now\); \d+ of \d+ carriers kept$")

    def test_a_pair_that_cannot_be_patched_is_routed_again(self):
        text = (SMELT.replace("pipes = AsmRow", SMELT2)
                .replace("ore -> smelt", "ore -> smelt, smelt2")
                .replace("coal -> smelt", "coal -> smelt, smelt2"))
        with mock.patch.object(route._Patch, "add_consumer", return_value=None):
            r = self.patched(text)
        self.assertEqual((r.routed, r.patched), ([PAIR], {}))
        self.assertIn("patching it failed: no branch from the standing route reaches smelt2.in1",
                      r.again[PAIR])


class WrongLaneTest(unittest.TestCase):
    """The live look: an item on a lane whose nets don't carry it is WRONG_ITEM (CORE-V2: no
    leniency for the right belt in the wrong lane)."""

    def look(self, lanes_):
        mini = MINI.replace("e ~iron/b2 transport-belt 4.5,0.5 E net=iron",
                            "e ~iron/b2 transport-belt 4.5,0.5 E net=iron|gear")
        s = compose.compose(fkp.loads(test_sense.SURFACE), {"mini": fkp.loads(mini)}, CAT)
        live = copy.deepcopy(test_sense.live_as_designed(s))
        belt = test_sense.find(live, "transport-belt", 14.5, 0.5)
        belt["lanes"] = lanes_
        belt["items"] = {i: n for lane in lanes_ for i, n in lane.items()}
        rep = sense.sense(s, live, CAT, test_sense.AREA, test_sense.WATCH,
                          net_items=test_sense.NETS)
        return next(v for v in rep.verdicts if v.key == "nauvis:mini/~iron/b2").wrong_items

    def test_each_lane_its_own_net(self):
        self.assertEqual(self.look([{"iron-plate": 3}, {"iron-gear-wheel": 2}]), [])
        self.assertEqual(self.look([{"iron-gear-wheel": 1}, {}]), ["iron-gear-wheel"])
        self.assertEqual(self.look([{}, {"iron-plate": 1, "copper-plate": 1}]),
                         ["copper-plate", "iron-plate"])


class RatesCommandTest(unittest.TestCase):
    """``fk rates`` shows the routed section on the .fkp the last build laid out."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fklanes-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def rates(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["rates", os.path.join(self.dir, "t.fk"), "--hand", "1",
                                       "--bulk-hand", "1"]), 0)
        return out.getvalue()

    def test_routed_section(self):
        with open(os.path.join(self.dir, "t.fk"), "w", encoding="utf-8") as fh:
            fh.write(SMELT)
        self.assertIn("no routed rates: t.fkp has no routes yet", self.rates())
        flat, r = routed_layout()
        fkp.save(r.layout, os.path.join(self.dir, "t.fkp"), CAT)
        text = self.rates()
        self.assertIn("routed t (V2: the lanes and inserters as laid)", text)
        self.assertIn("on t.fkp as last laid out", text)
        self.assertRegex(text, r"ore_ +iron-ore .*\.L \(yellow lanes\)")
        self.assertIn("inserter hands as given", text)


class InserterCatalogTest(unittest.TestCase):
    def test_the_catalog_carries_the_game_values(self):
        self.assertEqual(CAT.entity("fast-inserter")["rotation_speed"], 0.04)
        self.assertEqual(CAT.entity("stack-inserter")["stack_size_bonus"], 4)
        self.assertTrue(CAT.entity("bulk-inserter")["bulk"])
        self.assertAlmostEqual(lanes.inserter_rate("fast-inserter", cat=CAT), 2.5)
        self.assertAlmostEqual(lanes.inserter_rate("stack-inserter", cat=CAT), 12.5)
        self.assertAlmostEqual(lanes.inserter_rate("bulk-inserter", bulk_hand=4, cat=CAT), 10.0)

    def test_an_inserter_only_the_catalog_knows(self):
        data = {"entities": [{"name": "modded-inserter", "type": "inserter", "tile_width": 1,
                              "tile_height": 1, "rotation_speed": 0.05, "bulk": False,
                              "stack_size_bonus": 1}], "recipes": []}
        cat = Catalog.from_dict(data)
        swing = 2 * 10                                      # floor(0.5 / 0.05) = 10 ticks a way
        self.assertAlmostEqual(lanes.inserter_rate("modded-inserter", cat=cat), 60 / swing * 2)
        self.assertIsNone(lanes.inserter_rate("modded-inserter"))


if __name__ == "__main__":
    unittest.main()
