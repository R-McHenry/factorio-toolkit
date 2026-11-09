"""40-layout (PLAN-4.0 part P): routability-driven layout. The Lagrangian loop places a two-machine
net adjacent, spreads a crowded fan-out, never overlaps footprints, keeps ports and fixed instances,
is deterministic, and the Rust kernel agrees with the Python reference on random specs; `fk layout`
rewrites hints in place and the written mall builds and routes every net; the example's quoted output
in EXAMPLES.md is what the command prints. PLAN-ORGANIC R: the pair stem (R1), `--from out` reading
the last build's real carriers and negotiation history (R2), and the loop by hand (R3)."""
import io
import os
import random
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from fkcore import design, flow, layout
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file
from fkcore.layout import Params, Spec, SpecInst, SpecNet, _place_py, place

CAT = Catalog.load()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "agent", "docs", "examples")
DOCS = os.path.join(ROOT, "agent", "docs")
#: the grove (megabelt's circuit river reach, a copy of lab-session's fk-run2 for the R1 bar)
GROVE = os.path.join(ROOT, "tests", "data", "grove")


def square(w, h, groups=1):
    """A w x h instance with ``groups`` ring attach groups (a belt two tiles out, anywhere round
    it, its inserter's tile between)."""
    shapes = []
    for rot in range(4):
        ww, hh = (w, h) if rot % 2 == 0 else (h, w)
        tiles = [(x, y) for y in range(hh) for x in range(ww)]
        shapes.append((tiles, [layout._ring(ww, hh) for _ in range(groups)]))
    return shapes


def belt_end(w, h):
    """A w x h instance (a row) with one one-tile attach group: its belt end's tile just south of
    the footprint, so the tile beyond it (and a pair's stem run) lies further south."""
    shapes = []
    for rot in range(4):
        ww, hh = (w, h) if rot % 2 == 0 else (h, w)
        tiles = [(x, y) for y in range(hh) for x in range(ww)]
        shapes.append((tiles, [[(0, hh)]]))
    return shapes


def footprint(spec, res, i):
    at = res.at[i]
    return {(at[0] + dx, at[1] + dy) for dx, dy in spec.insts[i].shapes[at[2]][0]}


def no_overlap(test, spec, res):
    x0, y0, x1, y1 = spec.box
    seen = {}
    for i in range(len(spec.insts)):
        if res.at[i] is None:
            continue
        for t in footprint(spec, res, i):
            test.assertTrue(x0 <= t[0] < x1 and y0 <= t[1] < y1, f"{spec.insts[i].name} off the box")
            test.assertNotIn(t, seen, f"{spec.insts[i].name} overlaps {seen.get(t)}")
            test.assertNotIn(t, set(spec.blocked))
            seen[t] = spec.insts[i].name


def random_spec(seed, n_inst=6, box=22, sweeps=6, pairs=False):
    """``pairs``: every other instance is a belt end (a one-tile attach) and every other net a
    pair with a stem demand on its consumer (layout rule 5)."""
    rnd = random.Random(seed)
    insts, nets = [], []
    for i in range(n_inst):
        w, h = rnd.randint(1, 4), rnd.randint(1, 3)
        placed = rnd.random() < 0.3
        at = (rnd.randint(1, box - w - 2), rnd.randint(1, box - h - 2), 0) if placed else None
        shapes = belt_end(w, h) if pairs and i % 2 else square(w, h)
        insts.append(SpecInst(f"i{i}", shapes, at, at is None or rnd.random() < 0.5))
    for n in range(n_inst):
        a, b = rnd.sample(range(n_inst), 2)
        stem = rnd.randint(1, 4) if pairs and n % 2 else 0
        nets.append(SpecNet(f"n{n}", rnd.randint(1, 2), [(a, 0, True), (b, 0, False)], stem))
    blocked = [(rnd.randint(0, box - 1), rnd.randint(0, box - 1)) for _ in range(rnd.randint(0, 6))]
    return Spec((0, 0, box, box), blocked, insts, nets, Params(sweeps=sweeps))


def priced_spec(seed):
    """A random spec (pairs too) with a seeded price field on random tiles (R2)."""
    spec = random_spec(seed, pairs=bool(seed % 2))
    rnd = random.Random(seed * 7 + 1)
    box = spec.box[2]
    spec.price = [((rnd.randint(-1, box), rnd.randint(-1, box)), rnd.randint(1, 8) * 500)
                  for _ in range(rnd.randint(1, 30))]
    return spec


class PlaceTest(unittest.TestCase):
    def test_two_machines_end_adjacent(self):
        spec = Spec((0, 0, 20, 20), [],
                    [SpecInst("a", square(3, 3), None, True), SpecInst("b", square(3, 3), None, True)],
                    [SpecNet("ab", 1, [(0, 0, True), (1, 0, False)])], Params(sweeps=10))
        res = _place_py(spec)
        no_overlap(self, spec, res)
        self.assertEqual(res.unreached, [])
        self.assertLessEqual(res.after[0], layout.MILLI, "the two machines should share a belt tile")
        fa, fb = footprint(spec, res, 0), footprint(spec, res, 1)
        gap = min(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p in fa for q in fb)
        self.assertLessEqual(gap, 4, "inserter, belt, inserter between them at most")

    def test_crowded_fan_out_spreads(self):
        """One driver, five consumers in a row east of it: every relaxed route runs the same row.
        The loop pulls them round the driver: fewer hot tiles, shorter belts, no overlap."""
        insts = [SpecInst("src", square(1, 1), (1, 10), False)]
        insts[0].at = (1, 10, 0)
        for k in range(5):
            insts.append(SpecInst(f"c{k}", square(1, 1), (8 + 2 * k, 10, 0), True))
        nets = [SpecNet(f"n{k}", 1, [(0, 0, True), (k + 1, 0, False)]) for k in range(5)]
        spec = Spec((0, 0, 24, 21), [], insts, nets, Params(sweeps=12))
        start = _place_py(Spec(spec.box, [], insts, nets, Params(sweeps=0)))
        res = _place_py(spec)
        no_overlap(self, spec, res)
        self.assertEqual(res.at[0], (1, 10, 0), "a fixed instance never moves")
        self.assertGreater(len(start.hot), 0, "the row shares tiles at the start")
        self.assertLess(len(res.hot), len(start.hot))
        self.assertLess(sum(res.after), sum(res.before))
        ys = {res.at[i][1] for i in range(1, 6)}
        self.assertGreater(len(ys), 1, "the consumers spread off the one row")

    def test_ports_stay_and_are_never_covered(self):
        port = SpecInst("m/in", [([], [[(0, 5)]])] * 4, (0, 0, 0), False)
        port2 = SpecInst("m/out", [([], [[(15, 5)]])] * 4, (0, 0, 0), False)
        a = SpecInst("a", square(3, 3), None, True)
        b = SpecInst("b", square(3, 3), None, True)
        spec = Spec((0, 0, 16, 12), [], [port, port2, a, b],
                    [SpecNet("fe", 1, [(0, 0, True), (2, 0, False)]),
                     SpecNet("x", 1, [(2, 0, True), (3, 0, False)]),
                     SpecNet("out", 1, [(3, 0, True), (1, 0, False)])], Params(sweeps=8))
        res = _place_py(spec)
        no_overlap(self, spec, res)
        self.assertEqual(res.at[0], (0, 0, 0))
        self.assertEqual(res.at[1], (0, 0, 0))
        for i in (2, 3):
            self.assertNotIn((0, 5), footprint(spec, res, i))
            self.assertNotIn((15, 5), footprint(spec, res, i))
        self.assertEqual(res.unreached, [])

    def test_no_fit_is_none_not_an_error(self):
        spec = Spec((0, 0, 4, 4), [], [SpecInst("big", square(6, 6), None, True)], [], Params(sweeps=2))
        res = _place_py(spec)
        self.assertEqual(res.at, [None])

    def test_deterministic_and_no_overlap_on_random_specs(self):
        for seed in range(4):
            with self.subTest(seed=seed):
                spec = random_spec(seed, pairs=bool(seed % 2))
                a, b = _place_py(spec), _place_py(spec)
                self.assertEqual(a, b)
                no_overlap(self, spec, a)
                for i, inst in enumerate(spec.insts):
                    if not inst.movable and inst.at is not None:
                        self.assertEqual(a.at[i], tuple(inst.at))


class StemTest(unittest.TestCase):
    """Rule 5 (PLAN-ORGANIC R1): a `lanes A | B` pair's consumer belt end demands ``SpecNet.stem``
    free tiles straight beyond it, none another's belt end; the number is lanephys's."""

    def spec(self, stem, blocked=(), extra=()):
        row = SpecInst("row", belt_end(3, 1), (5, 5, 0), True)          # belt end at (5, 6)
        src = SpecInst("src", [([], [[(1, 1)]])] * 4, (0, 0, 0), False)  # a port, far away
        nets = [SpecNet("a|b", 1, [(1, 0, True), (0, 0, False)], stem)]
        return Spec((0, 0, 16, 16), list(blocked), [row, src] + list(extra), nets, Params(sweeps=2))

    def usable(self, spec):
        st = layout._State(spec)
        for i, inst in enumerate(spec.insts):
            if inst.at is not None:
                st.put(i, tuple(inst.at))
        return st.usable(0, (5, 5, 0), 0, (5, 6))

    def test_build_spec_reads_lanephys(self):
        from fkcore import lanephys
        self.assertGreater(lanephys.STEM, 0)
        with open(layout.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotRegex(src, r"stem\s*=\s*\d", "layout.py writes no lane number of its own")

    def test_blocked_stem_is_not_usable(self):
        # the run beyond (5, 6) is (5, 7), (5, 8), (5, 9) for a stem of 3
        self.assertTrue(self.usable(self.spec(3)))
        for t in ((5, 7), (5, 8), (5, 9)):
            self.assertFalse(self.usable(self.spec(3, blocked=[t])), f"blocked at {t}")
        self.assertTrue(self.usable(self.spec(3, blocked=[(5, 10)])), "past the run")
        self.assertTrue(self.usable(self.spec(3, blocked=[(6, 8)])), "beside the run")
        self.assertFalse(self.usable(self.spec(0, blocked=[(5, 7)])), "rule 2 still holds")
        self.assertTrue(self.usable(self.spec(0, blocked=[(5, 8)])), "no pair: no stem")

    def test_belt_end_on_the_stem_is_not_usable(self):
        port = SpecInst("p", [([], [[(5, 8)]])] * 4, (0, 0, 0), False)
        self.assertFalse(self.usable(self.spec(3, extra=[port])))
        self.assertTrue(self.usable(self.spec(1, extra=[port])), "a shorter stem ends before it")

    def test_stem_runs_inside_the_box(self):
        row = SpecInst("row", belt_end(3, 1), (5, 13, 0), True)          # belt end at (5, 14)
        src = SpecInst("src", [([], [[(1, 1)]])] * 4, (0, 0, 0), False)
        spec = Spec((0, 0, 16, 16), [], [row, src],
                    [SpecNet("a|b", 1, [(1, 0, True), (0, 0, False)], 3)], Params(sweeps=2))
        st = layout._State(spec)
        st.put(0, (5, 13, 0))
        self.assertFalse(st.fits(0, (5, 13, 0)), "the run would leave the box")
        self.assertTrue(st.fits(0, (5, 11, 0)))

    def test_placed_consumer_keeps_its_stem_free(self):
        """A belt end pulled towards a driver port on the box's south edge stops short of it:
        the stem stays free (the room a pair's trunk root needs)."""
        row = SpecInst("row", belt_end(3, 1), None, True)
        port = SpecInst("p", [([], [[(6, 15)]])] * 4, (0, 0, 0), False)
        for stem in (0, 3):
            spec = Spec((0, 0, 16, 16), [], [row, port],
                        [SpecNet("a|b", 1, [(1, 0, True), (0, 0, False)], stem)], Params(sweeps=6))
            res = _place_py(spec)
            no_overlap(self, spec, res)
            self.assertEqual(res.unreached, [])
            x, y, rot = res.at[0]
            end_y = y + (1 if rot % 2 == 0 else 3)
            if stem:
                self.assertLessEqual(end_y + stem, 14, "three free tiles before the port's row")
            else:
                self.assertEqual(end_y, 14, "without the rule the belt end meets the port")


@unittest.skipUnless(layout.native_on(), "no fkroute with place")
class ParityTest(unittest.TestCase):
    def test_python_and_rust_agree(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                spec = random_spec(seed + 10)
                self.assertEqual(layout._place_native(spec), _place_py(spec))

    def test_python_and_rust_agree_on_pairs(self):
        """Rule 5 step for step: random specs with belt ends and stem demands."""
        for seed in range(6):
            with self.subTest(seed=seed):
                spec = random_spec(seed + 20, pairs=True)
                self.assertIsNotNone(layout._stems(spec))
                self.assertEqual(layout._place_native(spec), _place_py(spec))

    def test_python_and_rust_agree_on_prices(self):
        """R2: a seeded price field, step for step."""
        for seed in range(6):
            with self.subTest(seed=seed):
                spec = priced_spec(seed + 30)
                self.assertTrue(spec.price)
                self.assertEqual(layout._place_native(spec), _place_py(spec))

    def test_check_mode_runs_both(self):
        os.environ["FK_NATIVE"] = "check"
        try:
            place(random_spec(99, n_inst=4, sweeps=3))
            place(random_spec(98, n_inst=4, sweeps=3, pairs=True))
            place(priced_spec(97))
        finally:
            del os.environ["FK_NATIVE"]


class PriceTest(unittest.TestCase):
    """R2: ``Spec.price`` seeds the price field (the last build's fought-over tiles): the walk pays
    it, and a movable instance settles off the priced corridor."""

    def test_seed_is_read_and_paid(self):
        a = SpecInst("a", square(1, 1), (2, 8, 0), False)
        b = SpecInst("b", square(1, 1), (12, 8, 0), False)
        spec = Spec((0, 0, 16, 16), [], [a, b], [SpecNet("ab", 1, [(0, 0, True), (1, 0, False)])],
                    Params(sweeps=1), [((7, 8), 3000), ((7, 8), 2000), ((99, 99), 5000)])
        st = layout._State(spec)
        st.put(0, (2, 8, 0))
        st.put(1, (12, 8, 0))
        self.assertEqual(st.price[st.idx((7, 8))], 3000, "the larger seed stands")
        plain, _r, _u = st.eval_net(0, priced=False)
        priced, _r, _u = st.eval_net(0, priced=True)
        self.assertEqual(priced, plain + 2 * layout.MILLI,
                         "one priced tile in the way: the walk goes round it (two tiles) rather "
                         "than pay the three")
        spec.price = [((x, y), 3000) for x in range(4, 11) for y in range(0, 16)]
        st2 = layout._State(spec)
        st2.put(0, (2, 8, 0))
        st2.put(1, (12, 8, 0))
        priced2, _r, _u = st2.eval_net(0, priced=True)
        self.assertGreater(priced2, plain, "a priced wall across the board is paid")

    def test_seed_pushes_off_the_corridor(self):
        """A fixed row's belt end at (3, 10) drives a movable row's belt end. Unpriced the consumer
        sits beside it (one tile of belt, body in row 9); with rows 9 to 12 priced as a fought-over
        corridor it settles north of them, where the walk reaches by a tunnel under the driver's
        body for three tiles instead of paying twenty for one."""
        def run(price):
            drv = SpecInst("d", belt_end(1, 1), (3, 9, 0), False)       # belt end at (3, 10)
            m = SpecInst("m", belt_end(1, 1), None, True)
            spec = Spec((0, 0, 20, 17), [], [drv, m],
                        [SpecNet("n", 1, [(0, 0, True), (1, 0, False)])], Params(sweeps=20), price)
            res = _place_py(spec)
            no_overlap(self, spec, res)
            self.assertEqual(res.unreached, [])
            return res.at[1]
        plain = run([])
        self.assertIn(plain[1], range(9, 13), f"unpriced: beside the driver's belt end: {plain}")
        corridor = [((x, y), 20 * layout.MILLI) for x in range(0, 20) for y in range(9, 13)]
        pushed = run(corridor)
        self.assertLessEqual(pushed[1], 7, f"off the priced rows, north of the driver: {pushed}")


class HintLineTest(unittest.TestCase):
    def test_replace_add_and_keep_comments(self):
        self.assertEqual(layout.hint_line("a = Chest<provider, limit=4>  @(18, 3)\n", (2, 3, 0)),
                         "a = Chest<provider, limit=4> @(2, 3)\n")
        self.assertEqual(layout.hint_line("a = Chest<provider>\n", (2, 3, 1)),
                         "a = Chest<provider> @(2, 3, rot 1)\n")
        self.assertEqual(layout.hint_line("pipe  = AsmRow<n=2, recipe=pipe>     # two\n", (4, 11, 2)),
                         "pipe  = AsmRow<n=2, recipe=pipe> @(4, 11, rot 2) # two\n")
        self.assertEqual(layout.hint_line("m = Mod size 7x3\n", (1, 1, 0)), "m = Mod @(1, 1) size 7x3\n")
        self.assertEqual(layout.hint_line('g = Gate<items=a|b, if="x > 1">', (0, 0, 3)),
                         'g = Gate<items=a|b, if="x > 1"> @(0, 0, rot 3)')


def stripped_mall(folder, name="layout"):
    """mall.fk with no hints, as ``name``.fk in ``folder`` (beside every example file)."""
    for f in os.listdir(EX):
        p = os.path.join(EX, f)
        if os.path.isdir(p):
            shutil.copytree(p, os.path.join(folder, f))
        else:
            shutil.copy(p, folder)
    with open(os.path.join(EX, "mall.fk"), encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r" *@\([^)]*\)", "", text)
    path = os.path.join(folder, name + ".fk")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def paper_build(folder, name, plot="34x44"):
    """The docs test's paper build of ``folder/name.fk``: (code, summary line, carriers)."""
    from tests.test_examples_docs import SCRIPT
    with open(os.path.join(folder, "nauvis.build.fkb"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SCRIPT)
    with open(os.path.join(folder, "nauvis.surface"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"surface nauvis\nterrain none\nplace {name} = {name} plot 0,0 {plot}\n")
    code, ctx = flow.run(os.path.join(folder, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
    summary = ""
    path = os.path.join(folder, "out", "report_checks.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            summary = next((l for l in fh.read().splitlines() if l.startswith(f"{name}: ")), "")
    from fkcore import fkp
    lay = fkp.load(os.path.join(folder, name + ".fkp"))
    carriers = sum(1 for e in lay.entities.values()
                   if e.name.endswith(("transport-belt", "underground-belt", "splitter")))
    return code, summary, carriers


def net_carriers(folder, name, nets=None):
    """The carriers the last build's route step laid for ``nets`` (default: every net) of
    ``folder/name.fk``, from the design database's net files: what `fk layout --from` reads. An
    instance's own belt (an AsmRow's) is no net's and is not counted."""
    recs = design.read_all(os.path.join(folder, "out"), name)
    return sum(1 for n, r in recs.items() if nets is None or n in nets
               for e in r["ents"] if e.name.endswith(("transport-belt", "underground-belt", "splitter")))


class CommandTest(unittest.TestCase):
    """`fk layout --write` on mall.fk with its hints removed: every instance placed, the file
    elaborates, and a paper build routes every net."""

    def test_write_round_trip_builds(self):
        d = tempfile.mkdtemp(prefix="fklayout-")
        self.addCleanup(shutil.rmtree, d, True)
        path = stripped_mall(d)
        flat = elaborate_file(path, CAT)
        self.assertTrue(all("at" not in i.hints for i in flat.insts.values()))
        lines, code = layout.layout_file(path, flat, CAT, write=True, plot=(34, 44))
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("layout layout: 11 instances, 11 placed now"), lines[0])
        self.assertTrue(any(l.startswith("  wrote 11 hints") for l in lines), lines)
        flat2 = elaborate_file(path, CAT)
        self.assertEqual(sorted(flat2.insts), sorted(flat.insts))
        self.assertTrue(all("at" in i.hints for i in flat2.insts.values()))
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text.count("@("), 11)
        self.assertIn("# mall.fk:", text, "the header comment is kept")
        # a second run keeps every hint: nothing to place
        lines2, _c = layout.layout_file(path, flat2, CAT, plot=(34, 44))
        self.assertIn("0 placed now, 0 kept, 11 fixed", lines2[0])
        code, summary, carriers = paper_build(d, "layout")
        self.assertEqual(code, 0)
        self.assertIn(" 0 unrouted", summary)
        self.assertIn(" 0 open", summary)
        self.assertGreater(carriers, 0)
        # R2's reading side: --from reads the build's net files (the nets' carriers; the AsmRow's
        # own belt is no net's), the report starts from them, and the placed instances move
        lines3, _c = layout.layout_file(path, flat2, CAT, plot=(34, 44),
                                        from_out=os.path.join(d, "out"))
        text = "\n".join(lines3)
        self.assertIn("0 fixed", lines3[0], "--from moves the placed instances (as --all)")
        self.assertIn("  from out/design/layout/nets: 8 of 8 nets routed by the last build; no "
                      "negotiation record", text)
        m = re.search(r"real belts (\d+) -> estimated \d+ over 8 nets", text)
        self.assertIsNotNone(m, text)
        real = net_carriers(d, "layout")
        self.assertLess(real, carriers, "the AsmRow's own belt is not a net's")
        self.assertEqual(int(m.group(1)), real, "the nets' carriers of the build")
        self.assertRegex(text, r"per net, real -> estimated: belts \d+ -> \d+, cab 0 -> 0, circs "
                               r"\d+ -> \d+, cu 0 -> 0, fe \d+ -> \d+")
        lines4, _c = layout.layout_file(path, flat2, CAT, plot=(34, 44),
                                        from_out=os.path.join(d, "nowhere"))
        self.assertTrue(any(l.startswith("  estimated belts ") for l in lines4), lines4)
        self.assertTrue(any("no net of layout was built there" in l for l in lines4), lines4)

    def test_cli_prints_source_lines(self):
        from fkcore import __main__ as cli
        d = tempfile.mkdtemp(prefix="fklayout-")
        self.addCleanup(shutil.rmtree, d, True)
        path = stripped_mall(d)
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["layout", path, "--plot", "34x44", "--sweeps", "1"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertRegex(text, r"\n  fein  = Chest<requester, item=iron-plate, rate=2/s> @\(\d+, \d+\)")
        self.assertIn("estimated belts", text)
        self.assertIn("1 sweeps", text)
        with open(path, encoding="utf-8") as fh:
            self.assertNotIn("@(", fh.read(), "without --write nothing is written")


class GroveTest(unittest.TestCase):
    """PLAN-ORGANIC R1's bar: grove.fk's four Stacks laid out from no hints inside Grove's frame.
    Each `lanes cu | fe` pair's consumer (a Stack's in_in belt end) keeps ``lanephys.STEM`` free
    tiles beyond it, and a paper build routes every net (76/76; 68/76 on 3.1.4) with no more
    carriers than the hand layout (256)."""

    def test_pairs_route_with_the_stem(self):
        from fkcore import lanephys
        d = tempfile.mkdtemp(prefix="fkgrove-")
        self.addCleanup(shutil.rmtree, d, True)
        for f in os.listdir(GROVE):
            shutil.copy(os.path.join(GROVE, f), d)
        path = os.path.join(d, "grove.fk")
        with open(path, encoding="utf-8") as fh:
            text = re.sub(r"(c\d = Stack<[^>]*>) *@\([^)]*\)", r"\1", fh.read())
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        flat = elaborate_file(path, CAT)
        built = layout.build_spec(flat, CAT, module="Grove")
        stems = {n.name: n.stem for n in built.spec.nets}
        self.assertEqual({k: v for k, v in stems.items() if v},
                         {f"g/cu{k}_|g/fe{k}_": lanephys.STEM for k in range(4)})
        lines, code = layout.layout_file(path, flat, CAT, module="Grove", write=True)
        self.assertEqual(code, 0)
        self.assertIn("4 placed now", lines[0])
        self.assertIn("every net reaches its consumers", "\n".join(lines))
        flat2 = elaborate_file(path, CAT)
        for k in range(4):
            x, y, _r = flat2.insts[f"g/c{k}"].hints["at"]
            # three GreenB cells of 7: the belt end's tile is row y + 21 (just below the foot),
            # the stem's run the STEM rows after it, inside the 40-tall frame (rows 0..39)
            self.assertLessEqual(int(y) + 21 + lanephys.STEM, 39, f"c{k} at {x},{y}")
        code, summary, carriers = paper_build(d, "grove", plot="46x40")
        self.assertEqual(code, 0)
        self.assertIn(" 0 unrouted", summary)
        self.assertIn(" 0 open", summary)
        self.assertLessEqual(carriers, 256, "no more carriers than the hand layout")
        # R2's reading side in module mode: the module's nets' real carriers from the net files
        lines2, _c = layout.layout_file(path, flat2, CAT, module="Grove",
                                        from_out=os.path.join(d, "out"))
        text = "\n".join(lines2)
        self.assertIn("  from out/design/grove/nets: 8 of 8 nets routed by the last build", text)
        m = re.search(r"real belts (\d+) -> estimated \d+ over 8 nets", text)
        self.assertIsNotNone(m, text)
        self.assertEqual(int(m.group(1)), net_carriers(d, "grove", {n.name for n in built.spec.nets}))
        self.assertRegex(text, r"per net, real -> estimated: g/cu0_\|g/fe0_ \d+ -> \d+")


class LoopTest(unittest.TestCase):
    """PLAN-ORGANIC R3, the loop by hand on the mall: round 1 `fk layout --write`, `fk build`;
    round 2 `fk layout --from out --write`, `fk build`. The tool never runs the build. The
    builds negotiate (FK_NEGOTIATE=1), so the route step writes the pressure record
    (``out/design/<factory>/pressure.json``) round 2 seeds its price field from; the second build
    has no more carriers than the first."""

    def test_two_rounds_do_not_get_worse(self):
        d = tempfile.mkdtemp(prefix="fkloop-")
        self.addCleanup(shutil.rmtree, d, True)
        os.environ["FK_NEGOTIATE"] = "1"
        self.addCleanup(os.environ.pop, "FK_NEGOTIATE", None)
        path = stripped_mall(d)
        out = os.path.join(d, "out")
        flat = elaborate_file(path, CAT)
        lines1, code = layout.layout_file(path, flat, CAT, write=True, plot=(34, 44))
        self.assertEqual(code, 0)
        code, summary1, _c = paper_build(d, "layout")
        self.assertEqual(code, 0)
        self.assertIn(" 0 unrouted", summary1)
        first = net_carriers(d, "layout")
        self.assertGreater(first, 0)
        pressure = design.read_pressure(out, "layout")
        self.assertIn("", pressure, "the top level negotiated and left its record")
        rec = pressure[""]
        self.assertEqual(rec["module"], "layout")
        self.assertIsNone(rec["key"], "the top level is no compile unit: no store key")
        self.assertGreaterEqual(rec["rounds"], 1)
        for x, y, h in rec["tiles"]:
            self.assertTrue(0 <= x < rec["frame"][0] and 0 <= y < rec["frame"][1], (x, y))
            self.assertGreater(h, 0)
        # round 2: from the build
        flat2 = elaborate_file(path, CAT)
        lines2, code = layout.layout_file(path, flat2, CAT, write=True, plot=(34, 44),
                                          from_out=out)
        self.assertEqual(code, 0)
        text = "\n".join(lines2)
        m = re.search(r"real belts (\d+) -> estimated (\d+) over 8 nets", text)
        self.assertIsNotNone(m, text)
        self.assertEqual(int(m.group(1)), first)
        if rec["tiles"]:
            self.assertRegex(text, rf"{len(rec['tiles'])} tiles fought over in {rec['rounds']} "
                                   r"negotiation rounds? seed the price field")
        else:
            self.assertIn("no tile fought over", text)
        code, summary2, _c = paper_build(d, "layout")
        self.assertEqual(code, 0)
        self.assertIn(" 0 unrouted", summary2)
        second = net_carriers(d, "layout")
        self.assertLessEqual(second, first, f"round 2 laid {second} carriers, round 1 {first}")
        self.assertEqual(design.read_pressure(out, "layout").get("", {}).get("rounds"),
                         rec["rounds"], "a build that lays nothing new keeps the record")

    def test_record_follows_what_stands(self):
        """The record is written when a step negotiated, kept when a step laid nothing, and
        removed when a step laid routes without negotiating."""
        d = tempfile.mkdtemp(prefix="fkpressure-")
        self.addCleanup(shutil.rmtree, d, True)
        units = {"": {"module": "m", "key": None, "frame": [4, 4], "rounds": 2, "pres": 2.0,
                      "tiles": [[1, 1, 1.0]]}}
        design.write_pressure(d, "m", units)
        self.assertEqual(design.read_pressure(d, "m"), units)
        design.write_pressure(d, "m", {}, routed=False)
        self.assertEqual(design.read_pressure(d, "m"), units)
        design.write_pressure(d, "m", {}, routed=True)
        self.assertEqual(design.read_pressure(d, "m"), {})
        design.write_pressure(d, "m", {}, routed=True)      # nothing there: no error


class ExampleTest(unittest.TestCase):
    """EXAMPLES.md's layout section quotes what `fk layout layout.fk --plot 34x44` prints (every
    line but the timing one), and the example's header names the command."""

    def test_docs_quote_the_output(self):
        path = os.path.join(EX, "layout.fk")
        self.assertTrue(os.path.exists(path))
        flat = elaborate_file(path, CAT)
        lines, code = layout.layout_file(path, flat, CAT, plot=(34, 44))
        self.assertEqual(code, 0)
        with open(os.path.join(DOCS, "EXAMPLES.md"), encoding="utf-8") as fh:
            docs = fh.read()
        for line in lines:
            if line.startswith("  took "):
                continue
            self.assertIn(line, docs, f"EXAMPLES.md does not quote: {line}")


if __name__ == "__main__":
    unittest.main()
