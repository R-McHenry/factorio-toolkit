"""The size step (1.6): ``n=auto`` rows get the fewest machines that meet the targets, the asserts
and what their consumers ask (Rory, 2026-10-21: "the original factory source code should have
been parametric for number of bldgs"), against numbers worked by hand.

Red science on assembling-machine-1 (speed 0.5): a pack takes 5 s, so 0.1/s a machine, and one
gear and one copper plate each. 1 pack/s: 10 red, 1 gear/s = 1 gear assembler (2 iron in 0.5 s,
1/s), 2 iron/s = 6.4 stone furnaces (3.2 s a plate: 0.3125/s) -> 7, 1 copper/s = 3.2 -> 4, ore
at 0.5/s a drill: 2/s = 4 iron drills, 1/s = 2 copper drills, coal 9.6 furnaces x 0.0225/s =
0.216/s = 1 drill."""
import os
import shutil
import tempfile
import unittest

from fkcore import __main__ as cli, flow, fkp, lang, rates, size
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate
from fkcore.lang import FkSyntaxError

CAT = Catalog.load()

RED = """
iron_ore   = MinerRow<n=auto, resource=iron-ore>            @(16, 2, rot 2)
copper_ore = MinerRow<n=auto, resource=copper-ore>          @(46, 2, rot 2)
coal       = MinerRow<n=auto, resource=coal>                @(64, 2, rot 2)
iron       = SmelterRow<n=auto, recipe=iron-plate>          @(16, 14)
copper     = SmelterRow<n=auto, recipe=copper-plate>        @(46, 14)
gears      = AsmRow<n=auto, recipe=iron-gear-wheel>         @(16, 26)
red        = AsmRow<n=auto, recipe=automation-science-pack> @(16, 38)
labs       = LabRow<n=10>                                   @(16, 50)
net iron_ore:   iron_ore -> iron
net copper_ore: copper_ore -> copper
net fuel:       coal -> iron, copper
net iron_p:     iron -> gears
net copper_p:   copper -> red
net gear:       gears -> red
net packs:      red -> labs
"""
HAND = {"iron_ore": 4, "copper_ore": 2, "coal": 1, "iron": 7, "copper": 4, "gears": 1, "red": 10}
ONE = {"automation-science-pack": 1.0}


def make(text):
    f = lang.parse(text, "t.fk")
    return lambda sizes: elaborate(f, dict(f.modules), CAT, "t", None, sizes)


def sized(text, targets=None, **kw):
    return size.size({"t": make(text)}, targets, **kw)


def counts(sz):
    return {r.path: r.n for r in sz.rows}


def row(sz, path):
    return next(r for r in sz.rows if r.path == path)


def want(sz, text):
    return next(w for w in sz.wants if w.text.startswith(text))


def line(sz, path):
    """The report's line of row ``path``."""
    return next(t for t in size.report(sz, CAT)[0] if t.startswith(f"  {path} "))


class LanguageTest(unittest.TestCase):
    def inst(self, text):
        return lang.parse(text, "t.fk").body.insts[0]

    def test_auto_and_its_bounds(self):
        a = self.inst("r = AsmRow<n=auto, recipe=pipe>").params["n"]
        self.assertEqual((a.lo, a.hi, a.top, str(a)), (1, None, lang.AUTO_TOP, "auto"))
        b = self.inst("r = AsmRow<n=auto 4..30, recipe=pipe> @(0, 0)").params["n"]
        self.assertEqual((b.lo, b.hi, str(b)), (4, 30, "auto 4..30"))
        self.assertEqual(self.inst("r = AsmRow<recipe=pipe, n=auto>").params["n"], lang.Auto())

    def test_bad_bounds_are_syntax_errors(self):
        for text, why in (("n=auto 5..2", "1 <= LO <= HI"), ("n=auto 0..3", "1 <= LO <= HI"),
                          ("n=auto 1.5..3", "whole numbers"), ("n=auto 3", "auto LO..HI"),
                          ("n=auto 3..", "auto LO..HI")):
            with self.assertRaises(FkSyntaxError, msg=text) as caught:
                lang.parse(f"r = AsmRow<{text}, recipe=pipe>", "t.fk")
            self.assertIn(why, str(caught.exception), text)

    def test_auto_counts_rows_only(self):
        for text in ("c = Chest<provider, rate=auto>", "a = Assembler<n=auto, recipe=pipe>"):
            with self.assertRaises(ElabError, msg=text) as caught:
                make(text)({})
            self.assertIn("auto is the count of a row", str(caught.exception))

    def test_elaborated_at_the_size_steps_count_else_the_layouts_else_its_low_bound(self):
        text = "r = AsmRow<n=auto 2..9, recipe=pipe> @(0, 0)\n"
        f = lang.parse(text, "t.fk")
        flat = elaborate(f, {}, CAT, "t")
        self.assertEqual((len(flat.insts["r"].machines), flat.insts["r"].params["n"],
                          flat.insts["r"].auto), (2, 2, (2, 9)))
        lay = fkp.loads("fkp 1 factory t\nsize 30x9\ninst r AsmRow n=7 recipe=pipe at 0,0 rot 0 "
                        "sig 0\n")
        self.assertEqual(len(elaborate(f, {}, CAT, "t", lay).insts["r"].machines), 7)
        self.assertEqual(len(elaborate(f, {}, CAT, "t", lay, {"r": 5}).insts["r"].machines), 5)
        self.assertEqual(len(elaborate(f, {}, CAT, "t", None, {"r": 40}).insts["r"].machines), 9)
        self.assertFalse(size.has_auto(elaborate(lang.parse("r = AsmRow<n=3, recipe=pipe>"), {},
                                                 CAT, "t")))


class RedScienceTest(unittest.TestCase):
    """n=auto on every row but the labs, and target automation-science-pack 1/s: the hand
    numbers of the module doc."""

    @classmethod
    def setUpClass(cls):
        cls.sz = sized(RED, ONE)

    def test_the_hand_numbers(self):
        self.assertEqual(counts(self.sz), HAND)
        self.assertTrue(all(w.ok for w in self.sz.wants), [w.text for w in self.sz.wants])
        model = self.sz.models["t"]
        self.assertAlmostEqual(model.inst_rate("red"), 1.0, places=9)
        self.assertEqual(len(self.sz.flats["t"].insts["red"].machines), 10)
        self.assertEqual(self.sz.flats["t"].insts["red"].params["n"], 10)

    def test_the_seed_is_plans_propagation_and_already_right(self):
        self.assertEqual({r.path: r.seed for r in self.sz.rows}, HAND)
        self.assertEqual(self.sz.grown, 0)
        autos = {("t", p): (1, lang.AUTO_TOP) for p in HAND}
        self.assertEqual(size.seed({"t": make(RED)({})}, autos, ONE),
                         {("t", p): n for p, n in HAND.items()})

    def test_what_each_count_serves(self):
        self.assertEqual(row(self.sz, "red").serves[0].text, "target automation-science-pack 1/s")
        iron = row(self.sz, "iron").serves
        self.assertEqual(iron[0].text, "net iron_p: iron-plate for gears")
        self.assertIn("target automation-science-pack 1/s", [w.text for w in iron])
        lines, checks = size.report(self.sz, CAT)
        self.assertEqual(lines[0], "sized: iron_ore n=4 (auto), copper_ore n=2 (auto), coal n=1 "
                                   "(auto), iron n=7 (auto), copper n=4 (auto), gears n=1 (auto), "
                                   "red n=10 (auto)")
        self.assertEqual(checks, [])
        text = "\n".join(lines)
        self.assertRegex(text, r"\n  red +AsmRow +10 +10 +1\.\.100  target "
                               r"automation-science-pack 1/s\n")
        self.assertRegex(text, r"\n  iron +SmelterRow +7 +7 +1\.\.100  net iron_p: iron-plate for "
                               r"gears \(for target automation-science-pack 1/s\)\n")
        self.assertIn("gears                AsmRow         1    1   1..100  its low bound, all of "
                      "it used: net gear: iron-gear-wheel for red", text)
        self.assertIn("its low bound, used 43%: what is asked of it takes less", text)   # coal
        self.assertIn("met     target automation-science-pack 1/s: 1.000/s", text)

    def test_from_any_start_the_grow_and_trim_steps_find_the_same(self):
        for start in (1, 30):
            sz = sized(RED, ONE, start={("t", p): start for p in HAND})
            self.assertEqual(counts(sz), HAND, start)
            self.assertTrue(all(w.ok for w in sz.wants), start)
        self.assertGreater(sized(RED, ONE, start={("t", p): 1 for p in HAND}).grown, 0)


class NetsTest(unittest.TestCase):
    """The design's actual nets: a shared net, fixed rows, sinks with a rate, duty, requester
    chests."""

    def test_a_shared_iron_net_is_sized_from_both_its_consumers(self):
        # circ n=2 (fixed) takes 1 iron/s each beside the gears' 2/s: 4/s = 12.8 furnaces
        text = RED.replace("net iron_p:     iron -> gears", "net iron_p:     iron -> gears, circ") + (
            "circ  = AsmRow<n=2, recipe=electronic-circuit>        @(34, 26)\n"
            "cable = Chest<requester, item=copper-cable, rate=10/s> @(30, 26)\n"
            "cbox  = Chest<provider>                               @(30, 34)\n"
            "net cab: cable -> circ\nnet circs: circ -> cbox\n")
        sz = sized(text, ONE)
        self.assertEqual(counts(sz), dict(HAND, iron=13, iron_ore=8))
        self.assertEqual(row(sz, "iron").serves[0].text, "net iron_p: iron-plate for gears, circ")
        st = sz.models["t"].nets[("iron_p", "iron-plate")]
        self.assertAlmostEqual(st.demand, 4.0, places=9)

    def test_fixed_rows_are_fed_without_a_target(self):
        sz = sized(RED.replace("red        = AsmRow<n=auto,", "red        = AsmRow<n=10,"))
        self.assertEqual(counts(sz), {k: v for k, v in HAND.items() if k != "red"})
        self.assertEqual(row(sz, "iron").serves[0].text, "net iron_p: iron-plate for gears")

    def test_nothing_asks_a_row_into_labs_for_more(self):
        sz = sized(RED)                                 # no target: one red, and what it takes
        self.assertEqual(counts(sz), dict(iron_ore=1, copper_ore=1, coal=1, iron=1, copper=1,
                                          gears=1, red=1))
        self.assertIn("its low bound, all of it used", line(sz, "red"))

    def test_duty_takes_more_machines(self):
        sz = sized(RED.replace("recipe=automation-science-pack>",
                               "recipe=automation-science-pack, duty=0.5>"), ONE)
        self.assertEqual(counts(sz), dict(HAND, red=20))

    def test_a_sink_with_a_rate_asks_its_rate(self):
        text = ("ore   = MinerRow<n=auto, resource=iron-ore>   @(10, 2, rot 2)\n"
                "coal  = MinerRow<n=auto, resource=coal>       @(30, 2, rot 2)\n"
                "smelt = SmelterRow<n=auto, recipe=iron-plate> @(10, 12)\n"
                "box   = Chest<provider, rate=2/s>             @(4, 22)\n"
                "net ore_: ore -> smelt\nnet fuel: coal -> smelt\nnet plates: smelt -> box\n")
        self.assertEqual(counts(sized(text)), {"ore": 4, "coal": 1, "smelt": 7})
        # a chest without a rate asks nothing: one furnace, and an assert sizes it instead
        plain = text.replace("rate=2/s", "limit=4")
        self.assertEqual(counts(sized(plain)), {"ore": 1, "coal": 1, "smelt": 1})
        sz = sized(plain + "assert smelt.rate >= 2/s\n")
        self.assertEqual(counts(sz), {"ore": 5, "coal": 1, "smelt": 7})   # 7 at full speed
        self.assertEqual(row(sz, "smelt").serves[0].text, "assert smelt.rate >= 120/min")

    def test_a_requester_at_its_rate_stops_the_chain(self):
        text = ("plates = Chest<requester, item=iron-plate, rate=1/s>    @(2, 2)\n"
                "copp   = Chest<requester, item=copper-plate>            @(2, 12)\n"
                "gears  = AsmRow<n=auto, recipe=iron-gear-wheel>         @(8, 2)\n"
                "red    = AsmRow<n=auto, recipe=automation-science-pack> @(8, 12)\n"
                "labs   = LabRow<n=3>                                    @(8, 23)\n"
                "net pl: plates -> gears\nnet cp: copp -> red\nnet gear: gears -> red\n"
                "net packs: red -> labs\n")
        sz = sized(text, ONE)
        self.assertEqual(counts(sz), {"gears": 1, "red": 5})      # the fewest for the 0.5/s it gets
        w = want(sz, "target")
        self.assertFalse(w.ok)
        self.assertAlmostEqual(w.value, 0.5, places=6)
        self.assertTrue(w.why.startswith("more red would run short: plates is a requester chest "
                                         "at 1.000/s (its rate=) (through net gear: "), w.why)
        checks = size.report(sz, CAT)[1]
        self.assertEqual([(c.code, c.where) for c in checks],
                         [("size", "target automation-science-pack 1/s")])
        self.assertIn("plates is a requester chest at 1.000/s", checks[0].msg)

    def test_an_unbounded_requester_leaves_the_row_at_its_low_bound(self):
        text = ("src  = Chest<requester, item=iron-plate>        @(2, 2)\n"
                "more = SmelterRow<n=auto, recipe=iron-plate>    @(8, 2)\n"
                "ore  = Chest<requester, item=iron-ore>          @(2, 12)\n"
                "coal = Chest<requester, item=coal>              @(2, 16)\n"
                "pipe = AsmRow<n=4, recipe=pipe>                 @(8, 12)\n"
                "box  = Chest<provider>                          @(2, 24)\n"
                "net plates: src, more -> pipe\nnet o: ore -> more\nnet f: coal -> more\n"
                "net pipes: pipe -> box\n")
        self.assertEqual(counts(sized(text)), {"more": 1})


class BoundsTest(unittest.TestCase):
    def test_a_row_stops_at_its_top_and_says_so(self):
        sz = sized(RED.replace("red        = AsmRow<n=auto,", "red        = AsmRow<n=auto 1..5,"),
                   ONE)
        self.assertEqual(counts(sz), dict(iron_ore=2, copper_ore=1, coal=1, iron=4, copper=2,
                                          gears=1, red=5))
        self.assertTrue(row(sz, "red").top)
        lines, checks = size.report(sz, CAT)
        self.assertIn("red n=5 (auto 1..5, at its top)", lines[0])
        self.assertEqual([(c.code, c.where, c.msg) for c in checks],
                         [("size", "target automation-science-pack 1/s",
                           "0.500/s: red is at n=5, the top of its auto 1..5")])

    def test_a_low_bound_is_kept(self):
        sz = sized(RED.replace("gears      = AsmRow<n=auto,", "gears      = AsmRow<n=auto 3..9,"),
                   ONE)
        self.assertEqual(counts(sz), dict(HAND, gears=3))
        self.assertIn("its low bound, used 33%: what is asked of it takes less", line(sz, "gears"))


class LabsTest(unittest.TestCase):
    def test_labs_with_a_rate_take_what_the_science_rows_make(self):
        sz = sized(RED.replace("labs       = LabRow<n=10>", "labs       = LabRow<n=auto, rate=2/min>"),
                   ONE)
        self.assertEqual(counts(sz), dict(HAND, labs=30))         # 1 pack/s at 1/30 each
        self.assertEqual(row(sz, "labs").serves[0].text,
                         "labs takes the automation-science-pack of net packs")

    def test_fixed_labs_with_a_rate_hold_the_science_back(self):
        f = lang.parse(RED.replace("LabRow<n=10>", "LabRow<n=10, rate=2/min>").replace(
            "n=auto", "n=12"), "t.fk")
        model = rates.solve(elaborate(f, {}, CAT, "t"))
        self.assertAlmostEqual(model.inst_rate("red"), 10 / 30, places=9)
        self.assertEqual(model.binding["red/m0"], ("out", "automation-science-pack", "packs"))

    def test_labs_without_a_rate_ask_for_no_more(self):
        sz = sized(RED.replace("labs       = LabRow<n=10>", "labs       = LabRow<n=auto>"), ONE)
        self.assertEqual(row(sz, "labs").n, 1)
        self.assertIn("a lab takes every pack that reaches it (no rate=)",
                      "\n".join(size.report(sz, CAT)[0]))


class FitTest(unittest.TestCase):
    PLACES = {"t": type("P", (), {"w": 60, "h": 40, "rot": 0})()}

    def test_a_grown_row_into_the_next_one_and_past_the_plot(self):
        # 6 plates/s: 19.2 furnaces -> 20, 40 tiles; 6.0 ore/s: 12 drills, 18 tiles
        text = ("ore   = MinerRow<n=auto, resource=iron-ore>   @(0, 0, rot 2)\n"
                "coal  = MinerRow<n=1, resource=coal>          @(16, 0, rot 2)\n"
                "smelt = SmelterRow<n=auto, recipe=iron-plate> @(0, 10)\n"
                "box   = Chest<provider, rate=6/s>             @(30, 12)\n"
                "net ore_: ore -> smelt\nnet fuel: coal -> smelt\nnet plates: smelt -> box\n")
        sz = sized(text)
        self.assertEqual(counts(sz), {"ore": 12, "smelt": 20})
        checks = size.fit(sz, self.PLACES, CAT)
        self.assertEqual([(c.code, c.where, c.msg) for c in checks], [
            ("does-not-fit", "t ore", "n=12 (auto) makes it 18x7 at @(0, 0): its frame overlaps coal's "
                            "(3x4 at @(16, 0)) on 2x4 tiles"),
            ("does-not-fit", "t smelt", "n=20 (auto) makes it 40x7 at @(0, 10): its frame overlaps box's "
                              "(1x1 at @(30, 12)) on 1x1 tiles")])
        small = sized(text.replace("rate=6/s", "rate=1/s"))   # 4 furnaces, 2 drills: room enough
        self.assertEqual(size.fit(small, self.PLACES, CAT), [])
        # 10/s: 32 furnaces, 64 tiles, past the plot's 60 (two coal drills: one feeds 22 furnaces)
        wide = sized(text.replace("rate=6/s", "rate=10/s").replace("@(30, 12)", "@(4, 30)")
                     .replace("MinerRow<n=1, resource=coal>", "MinerRow<n=2, resource=coal>"))
        self.assertEqual(counts(wide), {"ore": 20, "smelt": 32})
        self.assertIn("n=32 (auto) makes it 64x7 at @(0, 10): it runs past plot t (60x40 in the "
                      "factory's frame), x to 64", [c.msg for c in size.fit(wide, self.PLACES, CAT)])


class FlowTest(unittest.TestCase):
    """The step in a build: out/size.txt, the counts placed, a rebuild that keeps them, does-not-fit, the
    belts after route, and a script without the step."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fksize-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def game(self, fk, surface_extra="", script=None, plot="96x64"):
        files = {"main.fk": fk,
                 "nauvis.surface": f"surface nauvis\nmode play\nterrain none\n"
                                   f"place main = main plot 0,0 {plot}\n{surface_extra}",
                 "nauvis.build.fkb": script or ("read_surface nauvis\nread_terrain none\n"
                                                "elaborate\nsize\nreport_rates\n"
                                                "place --keep pinned\nroute --only stale\n"
                                                "report_rates\nwrite_layout\n")}
        for name, text in files.items():
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        return os.path.join(self.dir, "nauvis.build.fkb")

    def read(self, *parts):
        with open(os.path.join(self.dir, *parts), encoding="utf-8") as fh:
            return fh.read()

    def build(self, script, **kw):
        code, ctx = flow.run(script, cat=CAT, echo=lambda _line: None, **kw)
        self.assertEqual(code, 0, ctx.log)
        return ctx

    def test_size_then_place_then_a_rebuild_keeps_the_counts(self):
        script = self.game(RED, "target automation-science-pack 1/s\n")
        ctx = self.build(script, to="size")
        self.assertIn("[ 4/9] size", ctx.log[-1])
        txt = self.read("out", "size.txt")
        self.assertIn("sized: iron_ore n=4 (auto), copper_ore n=2 (auto), coal n=1 (auto), "
                      "iron n=7 (auto), copper n=4 (auto), gears n=1 (auto), red n=10 (auto)", txt)
        self.assertNotIn("checks:", txt)
        ctx = self.build(script)
        lay = fkp.load(os.path.join(self.dir, "main.fkp"))
        self.assertEqual(lay.insts["red"].params["n"], "10")
        self.assertEqual(sum(1 for e in lay.entities.values() if e.owner == "red"
                             and e.name == "assembling-machine-1"), 10)
        self.assertIn("target automation-science-pack 60/min: met", self.read("out",
                                                                              "report_rates.txt"))
        self.assertEqual([c.code for _s, c in ctx.checks if c.code in ("size", "does-not-fit", "target-not-met")],
                         [])
        first = self.read("main.fkp")
        self.build(script)
        self.assertEqual(self.read("main.fkp"), first)
        self.assertIn("8 unchanged", self.read("out", "place.txt"))
        self.assertNotIn("the committed layout has", self.read("out", "size.txt"))

    def test_a_new_target_grows_the_rows_and_says_by_how_much(self):
        script = self.game(RED, "target automation-science-pack 1/s\n")
        self.build(script)
        with open(os.path.join(self.dir, "nauvis.surface"), "a", encoding="utf-8") as fh:
            fh.write("target automation-science-pack 1.2/s\n")
        ctx = self.build(script, to="place")
        txt = self.read("out", "size.txt")
        self.assertIn("red n=12 (auto)", txt)
        self.assertIn("the committed layout has n=10: the row grows by 2", txt)
        self.assertIn("red: stale", self.read("out", "place.txt"))
        self.assertEqual(len(ctx.flats["main"].insts["red"].machines), 12)

    def test_from_place_sizes_again(self):
        script = self.game(RED, "target automation-science-pack 1/s\n")
        self.build(script, to="size")
        ctx = self.build(script, frm="place", to="place")
        self.assertEqual(len(ctx.flats["main"].insts["red"].machines), 10)
        self.assertIn("red", fkp.load(os.path.join(self.dir, "out", "place", "main.fkp")).insts)

    def test_a_row_grown_into_the_next_says_fit_and_place_stops(self):
        # 2 packs/s: 4 iron/s for the gears, 12.8 furnaces -> 13, x 16 to 42, into copper at 40
        script = self.game(RED.replace("@(46, 14)", "@(40, 14)"),
                           "target automation-science-pack 2/s\n")
        code, ctx = flow.run(script, cat=CAT, echo=lambda _line: None)
        self.assertEqual(code, 1)                               # place: two entities on a tile
        self.assertEqual(ctx.sized.counts("main"), dict(iron_ore=8, copper_ore=4, coal=1, iron=13,
                                                        copper=7, gears=2, red=20))
        fit = [c for s, c in ctx.checks if c.code == "does-not-fit"]
        self.assertEqual([(c.where, c.msg) for c in fit], [
            ("main iron", "n=13 (auto) makes it 26x7 at @(16, 14): its frame overlaps copper's "
                          "(14x7 at @(40, 14)) on 2x7 tiles")])
        self.assertTrue(ctx.log[-1].startswith("[ 6/9] place"), ctx.log)
        self.assertEqual({c.code for s, c in ctx.checks if s == "place"}, {"malformed"})

    def test_a_sized_net_past_a_yellow_lane_says_so_after_route(self):
        fk = ("ore   = MinerRow<n=auto, resource=iron-ore>      @(16, 2, rot 2)\n"
              "coal  = MinerRow<n=auto, resource=coal>          @(60, 2, rot 2)\n"
              "iron  = SmelterRow<n=auto, recipe=iron-plate>    @(16, 14)\n"
              "gears = AsmRow<n=5, recipe=iron-gear-wheel>      @(16, 26)\n"
              "box   = Chest<provider, limit=4>                 @(10, 38)\n"
              "net ore_: ore -> iron\nnet fuel: coal -> iron\nnet iron_p: iron -> gears\n"
              "net gear: gears -> box\n")
        ctx = self.build(self.game(fk, plot="96x44"))
        self.assertEqual(ctx.sized.counts("main"), {"ore": 20, "coal": 2, "iron": 32})
        self.assertIn("net iron_p: 10.000/s at these counts (sized: iron), more than a yellow lane "
                      "carries (7.5/s)", self.read("out", "size.txt"))
        size_lines = [c for s, c in ctx.checks if c.code == "size"]
        self.assertEqual([(s, c.where) for s, c in ctx.checks if c.code == "size"],
                         [("report_rates", "main net iron_p")])
        self.assertIn("at the sized counts (iron n=32) it asks 10.00/s where its yellow lanes "
                      "carry 7.50/s (ratio 1.33)", size_lines[0].msg)

    def test_a_script_without_the_step_says_the_counts_stay(self):
        script = self.game(RED, "target automation-science-pack 1/s\n",
                           script="read_surface nauvis\nread_terrain none\nelaborate\n")
        ctx = self.build(script)
        size_checks = [c for _s, c in ctx.checks if c.code == "size"]
        self.assertEqual(len(size_checks), 1)
        self.assertIn("no size step in the build script: each keeps the count its .fkp laid out "
                      "last, else its low bound", size_checks[0].msg)
        self.assertEqual(len(ctx.flats["main"].insts["red"].machines), 1)

    def test_a_design_without_auto_rows_is_as_written(self):
        script = self.game(RED.replace("n=auto", "n=3"))
        ctx = self.build(script, to="size")
        self.assertIsNone(ctx.sized)
        self.assertIn("no n=auto rows: every count is as written", self.read("out", "size.txt"))

    def test_the_example_builds_and_says_what_stops_it(self):
        # agent/docs/examples/sized.fk, as EXAMPLES.md says: 1 gear, 10 red, 10 labs, 4 nets
        path = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples",
                            "sized.fk")
        with open(path, encoding="utf-8") as fh:
            fk = fh.read()
        script = self.game(fk, plot="42x32")
        ctx = self.build(script)
        self.assertEqual(ctx.sized.counts("main"), {"gears": 1, "red": 10, "labs": 10})
        self.assertIn("main: 4 routed, 0 kept (0 pinned from the committed .fkp), 0 failed",
                      self.read("out", "route.txt"))
        self.assertEqual([c.code for _s, c in ctx.checks if c.code in ("size", "does-not-fit", "no-route",
                                                                        "too-thin")], [])
        # 1.5 packs/s: the requesters give what 1/s takes (2 iron, 1 copper a second)
        with open(os.path.join(self.dir, "nauvis.surface"), "a", encoding="utf-8") as fh:
            fh.write("target automation-science-pack 1.5/s\n")
        code, ctx = flow.run(script, cat=CAT, echo=lambda _line: None, to="size")
        self.assertEqual(code, 0)
        checks = [(c.code, c.where, c.msg) for _s, c in ctx.checks if c.code in ("size", "does-not-fit")]
        self.assertEqual([c[:2] for c in checks], [("size", "target automation-science-pack 90/min")])
        self.assertIn("copper is a requester chest at 1.000/s (its rate=)", checks[0][2])
        self.assertEqual(ctx.sized.counts("main"), {"gears": 1, "red": 10, "labs": 10})

    def test_fk_rates_sizes_with_the_surface_beside_it(self):
        self.game(RED, "target automation-science-pack 1/s\n")
        out = []
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(cli.main(["rates", os.path.join(self.dir, "main.fk")]), 0)
        out = buf.getvalue()
        self.assertTrue(out.startswith("sized: iron_ore n=4 (auto)"), out[:200])
        self.assertIn("sized with the targets of nauvis.surface and its placed factories", out)
        self.assertRegex(out, r"\n  red +AsmRow +10 ")


class ScriptsTest(unittest.TestCase):
    """Every build script of the repo runs size after elaborate; an upgrade adds it."""

    def test_every_build_script_sizes_after_elaborate(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        scripts = [os.path.join(root, "kickoff", "template", "game", "nauvis.build.fkb")]
        games = os.path.join(root, "games")
        for name in sorted(os.listdir(games)):
            scripts += [os.path.join(games, name, f) for f in os.listdir(os.path.join(games, name))
                        if f.endswith(".build.fkb")]
        self.assertGreater(len(scripts), 5)
        for path in scripts:
            with open(path, encoding="utf-8") as fh:
                steps = [ln.cmd for ln in flow.parse(fh.read(), path)]
            self.assertEqual(steps[steps.index("elaborate") + 1], "size", path)

    def test_the_upgrade_adds_the_size_line_once(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kickoff"))
        import upgrade_run
        old = "read_surface nauvis\nelaborate                 # templates\nplace\n"
        new = upgrade_run._size(old)
        self.assertEqual([ln.cmd for ln in flow.parse(new)], ["read_surface", "elaborate", "size",
                                                              "place"])
        self.assertIsNone(upgrade_run._size(new))
        self.assertIsNone(upgrade_run._size("read_surface nauvis\n"))
        self.assertTrue(upgrade_run._size("elaborate").endswith("elaborate\n"
                                                                + upgrade_run.SIZE_LINE))


if __name__ == "__main__":
    unittest.main()
