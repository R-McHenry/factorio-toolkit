"""40-layout (PLAN-4.0 part P): routability-driven layout. The Lagrangian loop places a two-machine
net adjacent, spreads a crowded fan-out, never overlaps footprints, keeps ports and fixed instances,
is deterministic, and the Rust kernel agrees with the Python reference on random specs; `fk layout`
rewrites hints in place and the written mall builds and routes every net; the example's quoted output
in EXAMPLES.md is what the command prints."""
import io
import os
import random
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from fkcore import flow, layout
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file
from fkcore.layout import Params, Spec, SpecInst, SpecNet, _place_py, place

CAT = Catalog.load()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "agent", "docs", "examples")
DOCS = os.path.join(ROOT, "agent", "docs")


def square(w, h, groups=1):
    """A w x h instance with ``groups`` ring attach groups (an inserter anywhere round it)."""
    shapes = []
    for rot in range(4):
        ww, hh = (w, h) if rot % 2 == 0 else (h, w)
        tiles = [(x, y) for y in range(hh) for x in range(ww)]
        shapes.append((tiles, [layout._ring(ww, hh) for _ in range(groups)]))
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


def random_spec(seed, n_inst=6, box=22, sweeps=6):
    rnd = random.Random(seed)
    insts, nets = [], []
    for i in range(n_inst):
        w, h = rnd.randint(1, 4), rnd.randint(1, 3)
        placed = rnd.random() < 0.3
        at = (rnd.randint(1, box - w - 2), rnd.randint(1, box - h - 2), 0) if placed else None
        insts.append(SpecInst(f"i{i}", square(w, h), at, at is None or rnd.random() < 0.5))
    for n in range(n_inst):
        a, b = rnd.sample(range(n_inst), 2)
        nets.append(SpecNet(f"n{n}", rnd.randint(1, 2), [(a, 0, True), (b, 0, False)]))
    blocked = [(rnd.randint(0, box - 1), rnd.randint(0, box - 1)) for _ in range(rnd.randint(0, 6))]
    return Spec((0, 0, box, box), blocked, insts, nets, Params(sweeps=sweeps))


class PlaceTest(unittest.TestCase):
    def test_two_machines_end_adjacent(self):
        spec = Spec((0, 0, 20, 20), [],
                    [SpecInst("a", square(3, 3), None, True), SpecInst("b", square(3, 3), None, True)],
                    [SpecNet("ab", 1, [(0, 0, True), (1, 0, False)])], Params(sweeps=10))
        res = _place_py(spec)
        no_overlap(self, spec, res)
        self.assertEqual(res.unreached, [])
        self.assertLessEqual(res.after[0], layout.MILLI, "the two machines should share an inserter tile")
        fa, fb = footprint(spec, res, 0), footprint(spec, res, 1)
        gap = min(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p in fa for q in fb)
        self.assertLessEqual(gap, 2)

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
        port2 = SpecInst("m/out", [([], [[(11, 5)]])] * 4, (0, 0, 0), False)
        a = SpecInst("a", square(3, 3), None, True)
        b = SpecInst("b", square(3, 3), None, True)
        spec = Spec((0, 0, 12, 12), [], [port, port2, a, b],
                    [SpecNet("fe", 1, [(0, 0, True), (2, 0, False)]),
                     SpecNet("x", 1, [(2, 0, True), (3, 0, False)]),
                     SpecNet("out", 1, [(3, 0, True), (1, 0, False)])], Params(sweeps=8))
        res = _place_py(spec)
        no_overlap(self, spec, res)
        self.assertEqual(res.at[0], (0, 0, 0))
        self.assertEqual(res.at[1], (0, 0, 0))
        for i in (2, 3):
            self.assertNotIn((0, 5), footprint(spec, res, i))
            self.assertNotIn((11, 5), footprint(spec, res, i))
        self.assertEqual(res.unreached, [])

    def test_no_fit_is_none_not_an_error(self):
        spec = Spec((0, 0, 4, 4), [], [SpecInst("big", square(6, 6), None, True)], [], Params(sweeps=2))
        res = _place_py(spec)
        self.assertEqual(res.at, [None])

    def test_deterministic_and_no_overlap_on_random_specs(self):
        for seed in range(4):
            with self.subTest(seed=seed):
                spec = random_spec(seed)
                a, b = _place_py(spec), _place_py(spec)
                self.assertEqual(a, b)
                no_overlap(self, spec, a)
                for i, inst in enumerate(spec.insts):
                    if not inst.movable and inst.at is not None:
                        self.assertEqual(a.at[i], tuple(inst.at))


@unittest.skipUnless(layout.native_on(), "no fkroute with place")
class ParityTest(unittest.TestCase):
    def test_python_and_rust_agree(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                spec = random_spec(seed + 10)
                self.assertEqual(layout._place_native(spec), _place_py(spec))

    def test_check_mode_runs_both(self):
        os.environ["FK_NATIVE"] = "check"
        try:
            place(random_spec(99, n_inst=4, sweeps=3))
        finally:
            del os.environ["FK_NATIVE"]


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
