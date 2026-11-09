"""32-docs: the player docs are structured around examples (PLAN-DOCS, Rory 11-08), and tests keep
them true. Every agent/docs/examples/*.fk builds on paper as a player's `fk build --to
report_checks` does (the template's steps through report_checks, terrain none, the plot size the
chapter names), and the summary lines EXAMPLES.md (and START.md) quote for it are what the build
prints; the chapter-7 library table lists exactly the cells of cells.fk; every `fk X` in START.md,
EXAMPLES.md and TOOLKIT.md is a real command. The five-example test of 2.1 (test_examples_21) still
runs beside this one."""
import os
import re
import shutil
import tempfile
import unittest

from fkcore import flow, lang
from fkcore.catalog import Catalog

CAT = Catalog.load()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "agent", "docs")
EX = os.path.join(DOCS, "examples")
#: the template's steps up to report_checks (no run_models: it reads the game folder's models)
SCRIPT = """read_surface    nauvis
read_terrain    none
elaborate
size
report_rates
place           --keep pinned
route           --only stale --retry-failed changed --failed keep --effort normal --hand any
hands           minimize
tier            minimize --allow yellow
cover robots
cover power     --pole any
floorplan
report_checks
write_layout
"""
#: the plot each chapter names (200x200 where it says "any")
SIZES = {"gears": "16x16", "smelting": "26x26", "shared-belt": "26x23", "smelter-array": "33x50",
         "beltless": "13x7", "red": "30x30", "sized": "42x32", "mall": "34x44",
         "early-mall": "49x24", "compact-mall": "50x16", "bus4": "54x25", "busbase": "172x82",
         "furnace-column": "31x41", "robot-feed": "12x8", "steam": "16x26", "bus4ribs": "100x40",
         "blue6": "60x40", "beacon-cells": "44x40", "red-chain": "92x76", "belt-switch": "64x70",
         "mate": "40x40", "layout": "34x44", "territory": "40x40", "shape": "36x30"}
#: 40-layout: the examples with no `@(x, y)` hints, laid out with `fk layout --write` (as the
#: chapter does) before the paper build; the value is the module laid out in module mode
#: (`fk layout FILE MODULE`), None for the file's top level
LAID_OUT = {"layout": None, "territory": None, "shape": "Mod"}
#: 43-hull: an example the chapter builds in two steps: first with the file cut at the marker
#: line (the first build records the sealed modules' hulls), then whole; the summary line quoted
#: is the second build's
STEPS = {"shape": "# -- step 2"}
#: 43-mines (chapter 3): the examples that build on the terrain fixture `patch.terrain.json` with
#: its own script `patch.build.fkb` (the template's steps through `place`): their plot on it. They
#: are judged by the size, place and check lines the chapter quotes, not by a summary line
TERRAIN = {"ore-patch": "0,0 60x40", "mixed-patch": "0,40 60x40"}
#: the fk wrapper's own commands (agent/fk.py) besides fkcore's subcommands
WRAPPER = {"build", "look", "wait", "stage", "lab", "alone", "sim", "map", "capture", "catalog",
           "route", "place", "report", "compile", "lua", "stats"}
#: words after `fk` in the docs that are not commands (a sentence goes on)
NOT_COMMANDS = {"X", "commands", "command", "run", "is", "the", "and", "or", "a", "in", "to", "of",
                "lines", "build:", "lab:", "look:", "alone:", "wait:", "on", "build's", "look's",
                "lab's", "check's", "rates's", "status:", "route:", "seed:", "hold:", "paste:",
                "ack:", "sim:", "map:", "stage:", "walk:", "plan:", "explain:", "contract:",
                "measure:", "capture:", "adopt:", "robots:", "register:", "diff:", "placements:",
                "standin:", "compile:", "dnp:", "unfold:", "check:", "rates:", "says", "say:",
                "stock:", "capital:", "stats:", "chart:", "alerts:", "research:", "tech:",
                "recipes:", "chat:", "lua:", "fresh:", "decon:", "request:", "merge:",
                "read-terrain:", "unhold:", "unroute:", "migrate-origins:", "migrate-surface:",
                "catalog:", "steps", "step", "wrapper", "wrapper's"}


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def examples():
    return sorted(f[:-3] for f in os.listdir(EX) if f.endswith(".fk") and f != "cells.fk")


def paper_build(name):
    """A paper build of EX/<name>.fk in a scratch game folder with every example file beside it.
    -> (exit code, the report_checks summary line, the check lines, the folder)."""
    d = tempfile.mkdtemp(prefix="fkdocs-")
    for f in os.listdir(EX):
        p = os.path.join(EX, f)
        if os.path.isdir(p):
            shutil.copytree(p, os.path.join(d, f))
        else:
            shutil.copy(p, d)
    script, terrain, plot = SCRIPT, "none", f"0,0 {SIZES.get(name, '200x200')}"
    if name in TERRAIN:
        script, terrain, plot = read(EX, "patch.build.fkb"), "patch", TERRAIN[name]
    with open(os.path.join(d, "nauvis.build.fkb"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    with open(os.path.join(d, "nauvis.surface"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"surface nauvis\nterrain {terrain}\nplace {name} = {name} plot {plot}\n")
    if name in LAID_OUT:
        from fkcore import layout as layoutmod
        from fkcore.elaborate import elaborate_file
        src = os.path.join(d, name + ".fk")
        w, h = SIZES[name].split("x")
        layoutmod.layout_file(src, elaborate_file(src, CAT), CAT, module=LAID_OUT[name], write=True,
                              plot=None if LAID_OUT[name] else (int(w), int(h)))
    if name in STEPS:
        src = os.path.join(d, name + ".fk")
        with open(src, encoding="utf-8") as fh:
            whole = fh.read()
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(whole[:whole.index(STEPS[name])])
        flow.run(os.path.join(d, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(whole)
    code, ctx = flow.run(os.path.join(d, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
    summary = ""
    path = os.path.join(d, "out", "report_checks.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        summary = next((l for l in lines if l.startswith(f"{name}: ")), "")
    return code, summary, [(c.code, c.where, c.msg) for _s, c in ctx.checks], d


def squash(text):
    return re.sub(r"\s+", " ", text)


class ExamplesBuildTest(unittest.TestCase):
    """Every example builds on paper, and EXAMPLES.md quotes its summary line as the build prints
    it (START.md too for gears). Slow: about two minutes for the 26 files."""

    def test_every_example_builds_and_is_quoted_right(self):
        docs = squash(read(DOCS, "EXAMPLES.md"))
        start = squash(read(DOCS, "START.md"))
        for name in examples():
            if name in TERRAIN:
                continue
            with self.subTest(example=name):
                code, summary, checks, d = paper_build(name)
                self.addCleanup(shutil.rmtree, d, True)
                self.assertEqual(code, 0, f"{name}: the paper build stopped")
                self.assertTrue(summary, f"{name}: no summary line in report_checks.txt")
                self.assertIn(" 0 unrouted", summary)
                self.assertEqual([c for c in checks if c[0] in ("SPILL", "no-route", "malformed",
                                                                "cannot-carry")], [])
                self.assertIn(squash(summary), docs,
                              f"{name}: EXAMPLES.md does not quote the build's summary line:\n"
                              f"  {summary}")
                if name == "gears":
                    self.assertIn(squash(summary), start)

    def test_the_patch_examples_build_on_their_terrain(self):
        """43-mines (chapter 3): ore-patch.fk and mixed-patch.fk build to `place` on
        patch.terrain.json with patch.build.fkb, and the size, place and check lines the chapter
        quotes are the build's."""
        docs = squash(read(DOCS, "EXAMPLES.md"))
        for name in TERRAIN:
            with self.subTest(example=name):
                code, _summary, checks, d = paper_build(name)
                self.addCleanup(shutil.rmtree, d, True)
                self.assertEqual(code, 0, f"{name}: the build stopped")
                place = read(d, "out", "place.txt")
                placed = [l.strip() for l in place.splitlines() if l.strip().startswith("placed ")]
                self.assertEqual(len(placed), 1, place)
                self.assertIn(squash(placed[0]), docs, f"{name}: not quoted: {placed[0]}")
                mixed = [c for c in checks if c[0] == "mixed-patch"]
                if name == "ore-patch":
                    sized = read(d, "out", "size.txt")
                    self.assertIn("sized: ore n=14 (auto 4..30)", sized)
                    quoted = [l.strip() for l in sized.splitlines()
                              if l.startswith("sized:") or "@patch(iron-ore):" in l
                              or "on their ore by place" in l]
                    self.assertEqual(len(quoted), 3, sized)
                    for line in quoted:
                        self.assertIn(squash(line), docs, f"{name}: not quoted: {line}")
                    self.assertEqual(mixed, [])
                    self.assertIn("14/14 drills on iron-ore", placed[0])
                else:
                    self.assertEqual(len(mixed), 1, checks)
                    code_, where, msg = mixed[0]
                    self.assertIn(squash(f"{code_} {where}: {msg}"), docs, f"not quoted: {msg}")
                    self.assertIn("4 of 8 drills placed", msg)
                    self.assertTrue(placed[0].endswith("; 4 left out (mixed-patch)"), placed[0])

    def test_what_the_chapters_quote(self):
        """A few lines the chapters quote beyond the summary: the gates' amounts, the ribbon, the
        two power domains, the beaconed furnaces, the belt switch."""
        from fkcore.catalog import Catalog as C
        from fkcore.elaborate import elaborate_file
        docs = read(DOCS, "EXAMPLES.md")
        code, _s, checks, d = paper_build("mall-loop")
        self.addCleanup(shutil.rmtree, d, True)
        flat = elaborate_file(os.path.join(d, "mall-loop.fk"), C.load())
        self.assertEqual({n: g[1] for n, g in flat.gates.items()},
                         {"g1/s": 160, "g2/s": 40, "g3/s": 40})
        self.assertIn("auto holds iron-plate below 160: 40 s of the 4/s", docs)
        code, _s, _c, d = paper_build("ribbon-bus")
        self.addCleanup(shutil.rmtree, d, True)
        route = read(d, "out", "route.txt")
        ribbon = next(l for l in route.splitlines() if l.strip().startswith("ribbon "))
        self.assertIn(squash(ribbon.strip()), squash(docs))
        code, _s, _c, d = paper_build("power-shed")
        self.addCleanup(shutil.rmtree, d, True)
        cover = read(d, "out", "cover_power.txt")
        for line in ("domain labs: cover power-labs", "copper feed: power/p3 to sw/m0.left"):
            self.assertIn(line, cover)
            self.assertIn(line, docs)
        code, _s, checks, d = paper_build("belt-switch")
        self.addCleanup(shutil.rmtree, d, True)
        plan = read(d, "out", "floorplan.txt")
        self.assertIn("gated net bay/out_: 1 carrier if=steel-plate>0 on bay/sw", plan)
        self.assertIn("gated net bay/out_: 1 carrier if=steel-plate>0 on bay/sw", docs)
        self.assertEqual(sorted(c[0] for c in checks if c[0] in ("gate-open",)),
                         ["gate-open", "gate-open"])


class TwoRoundsTest(unittest.TestCase):
    """43-hierarchy (PLAN-ORGANIC D4, R3): the two-round stories are real builds, quoted exactly.
    Chapter 11: red-chain.fk built, `p1` moved a tile inside `PlasPair`, built again: PlasPair
    misses the store and says why, p1's nets come from the store, the rest stands. Chapter 9:
    layout.fk's round 2, `fk layout --from out`, reads the real carriers and moves nothing."""

    def test_a_change_inside_a_module_reroutes_only_itself(self):
        docs = squash(read(DOCS, "EXAMPLES.md"))
        code, summary1, _c, d = paper_build("red-chain")
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(code, 0)
        route1 = read(d, "out", "route.txt")
        self.assertIn(squash("red-chain: 85 routed, 0 kept, 33 pass-through (0 pinned from the "
                             "committed .fkp), 0 failed, 1 pass"), squash(route1))
        self.assertIn(squash("red-chain: 85 routed, 0 kept, 33 pass-through"), docs)
        src = os.path.join(d, "red-chain.fk")
        text = read(src)
        self.assertIn("  p1 = Plas2 @(0, 0)\n", text)
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace("  p1 = Plas2 @(0, 0)\n", "  p1 = Plas2 @(0, 1)\n"))
        code, _ctx = flow.run(os.path.join(d, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
        self.assertEqual(code, 0)
        route2 = read(d, "out", "route.txt")
        for line in (
                "red-chain: compiled  chain/pl: not in the store; PlasPair's last entry (faca6bf7) "
                "differs in instances, net coal_/goals, net gas/reserved, net plastic_a_/starts, "
                "standing",
                "red-chain: compiled  chain/pl/p1: 3 nets laid from the store (Plas2 "
                "2e368b5a3e23fea7f27b)",
                "red-chain: compiled  stored chain, chain/pl (out/compiled): laid from there "
                "wherever each stands next",
                "red-chain: 6 routed, 79 kept, 33 pass-through (83 pinned from the committed .fkp, "
                "3 laid from the compiled store), 0 failed, 1 pass"):
            self.assertIn(squash(line), squash(route2), line)
            self.assertIn(squash(line), docs, line)
        summary2 = next(l for l in read(d, "out", "report_checks.txt").splitlines()
                        if l.startswith("red-chain: "))
        self.assertIn(" 0 unrouted", summary2)
        self.assertIn(squash(summary2), docs, summary2)

    def test_the_layout_loop_reads_the_real_carriers(self):
        from fkcore import layout as layoutmod
        from fkcore.elaborate import elaborate_file
        from tests.test_layout import net_carriers, stripped_mall
        docs = squash(read(DOCS, "EXAMPLES.md"))
        d = tempfile.mkdtemp(prefix="fkdocs-loop-")
        self.addCleanup(shutil.rmtree, d, True)
        path = stripped_mall(d)
        with open(os.path.join(d, "nauvis.build.fkb"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(SCRIPT)
        with open(os.path.join(d, "nauvis.surface"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("surface nauvis\nterrain none\nplace layout = layout plot 0,0 34x44\n")
        lines1, code = layoutmod.layout_file(path, elaborate_file(path, CAT), CAT, write=True,
                                             plot=(34, 44))
        self.assertEqual(code, 0)
        self.assertIn("estimated belts 62 -> 4 over 8 nets", "\n".join(lines1))
        code, _ctx = flow.run(os.path.join(d, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
        self.assertEqual(code, 0)
        self.assertEqual(net_carriers(d, "layout"), 40)
        lines2, code = layoutmod.layout_file(path, elaborate_file(path, CAT), CAT, write=True,
                                             plot=(34, 44), from_out=os.path.join(d, "out"))
        self.assertEqual(code, 0)
        text2 = squash("\n".join(lines2))
        for line in ("layout layout: 11 instances, 0 placed now, 11 kept, 0 fixed; 8 nets; "
                     "frame 34x44 (--plot)",
                     "per net, real -> estimated: belts 15 -> 0, cab 0 -> 0, circs 10 -> 0, "
                     "cu 0 -> 0, fe 11 -> 3, gears 2 -> 0, inss 0 -> 0, pipes 2 -> 1",
                     "real belts 40 -> estimated 4 over 8 nets; every net reaches its consumers; "
                     "0 hot tiles; 4 sweeps"):
            self.assertIn(squash(line), text2, line)
            self.assertIn(squash(line), docs, line)
        code, _ctx = flow.run(os.path.join(d, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
        self.assertEqual(code, 0)
        self.assertEqual(net_carriers(d, "layout"), 39)
        route2 = squash(read(d, "out", "route.txt"))
        line = "layout: 0 routed, 7 kept, 1 patched (8 pinned from the committed .fkp), 0 failed, 1 pass"
        self.assertIn(line, route2)
        self.assertIn(line, docs)
        summary2 = next(l for l in read(d, "out", "report_checks.txt").splitlines()
                        if l.startswith("layout: "))
        self.assertIn(squash(summary2), docs, summary2)


class LibraryTableTest(unittest.TestCase):
    """Chapter 7's table lists exactly the modules and kinds of examples/cells.fk."""

    def test_table_equals_cells_fk(self):
        f = lang.parse(read(EX, "cells.fk"), "cells.fk")
        in_file = set(f.modules) | set(f.kinds)
        docs = read(DOCS, "EXAMPLES.md")
        table = docs[docs.index("| cell | what | ports |"):]
        table = table[:table.index("\n\n")]
        listed = set()
        for row in table.splitlines()[2:]:
            cell = row.split("|")[1]
            listed |= set(re.findall(r"`([A-Za-z0-9]+)", cell))
        self.assertEqual(listed, in_file, "the chapter-7 table and cells.fk differ")


class CommandsTest(unittest.TestCase):
    """Every `fk X` in the three docs names a real command."""

    def test_every_fk_word_is_a_command(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from fkcore import __main__ as cli
        import argparse
        names = set()
        orig = argparse.ArgumentParser.add_subparsers

        def grab(self_, **kw):
            sub = orig(self_, **kw)
            add = sub.add_parser

            def add_parser(name, **k):
                names.add(name)
                return add(name, **k)
            sub.add_parser = add_parser
            return sub
        argparse.ArgumentParser.add_subparsers = grab
        try:
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                try:
                    cli.main(["--help"])
                except SystemExit:
                    pass
        finally:
            argparse.ArgumentParser.add_subparsers = orig
        self.assertIn("check", names)
        real = names | WRAPPER
        bad = set()
        for doc in ("START.md", "EXAMPLES.md", "TOOLKIT.md"):
            for word in re.findall(r"(?<![.\w])fk ([A-Za-z][A-Za-z0-9_-]*:?)", read(DOCS, doc)):
                if word in NOT_COMMANDS or word.rstrip(":") in real:
                    continue
                bad.add((doc, word))
        self.assertEqual(bad, set())


class HeadersTest(unittest.TestCase):
    """Every example file opens with a header comment that names the command and what to expect."""

    def test_headers(self):
        for name in examples():
            with self.subTest(example=name):
                text = read(EX, name + ".fk")
                head = []
                for line in text.splitlines():
                    if not line.startswith("#"):
                        break
                    head.append(line)
                self.assertGreaterEqual(len(head), 3, f"{name}: no header comment")
                self.assertTrue(head[0].startswith(f"# {name}.fk:"), head[0])
                joined = "\n".join(head)
                self.assertIn("Run:", joined)
                self.assertIn("Expect:", joined)


if __name__ == "__main__":
    unittest.main()
