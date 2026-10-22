"""fk stage (fkcore.stage, 2.0): the lead's staged plan in git, its folders, checks and horizon.

Rory (2026-10-21/22, assessment-20261021/PLAN-AHEAD.md): main is what is built, the plan one
commit per stage ahead of it; replaying the plan onto reality is the key operation, and the horizon
(the planned base against the built one) says when planning is the lead's next job."""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from fkcore import flow, stage
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

ROOT = os.path.join(os.path.dirname(__file__), "..")
MERGE = os.path.join(ROOT, "games", "merge")
SURFACE = """surface  nauvis
mode     play
terrain  none
catalog  base

place iron  = iron  plot 0,0 20x24
"""
GEARS_PLACE = "place gears = gears plot 22,0 16x16\n"


def script_text():
    with open(os.path.join(ROOT, "games", "lab-play", "lab.build.fkb"), encoding="utf-8") as fh:
        return fh.read().replace("read_surface    lab ", "read_surface    nauvis")


class StageTest(unittest.TestCase):
    """A run folder of games/merge's iron factory (4 furnaces, 60 plates/min) as what is built."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkstage-test-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.game = os.path.join(self.dir, "game")
        os.makedirs(self.game)
        shutil.copy(os.path.join(MERGE, "iron.fk"), self.game)
        self.write("game/nauvis.surface", SURFACE)
        self.write("game/nauvis.build.fkb", script_text())

    @property
    def plan(self):
        """A fresh Plan, as each fk stage command has (a Plan caches refs within a command)."""
        return stage.Plan(self.game)

    def write(self, rel, text, mode="w"):
        path = os.path.join(self.dir, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode, encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def read(self, rel):
        with open(os.path.join(self.dir, *rel.split("/")), encoding="utf-8") as fh:
            return fh.read()

    def fk(self, *argv):
        """``fk stage ARGV`` -> its output; a code other than 0 fails the test."""
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = stage.main(self.game, list(argv))
        self.assertEqual(code, 0, buf.getvalue() + err.getvalue())
        return buf.getvalue()

    def git(self, *args):
        return self.plan.git(*args)

    def more_smelting(self, n):
        """Stage n's folder: 8 furnaces and 4 ore drills (120 plates/min)."""
        path = f"stages/{n}/iron.fk"
        self.write(path, self.read(path).replace("SmelterRow<n=4", "SmelterRow<n=8")
                   .replace("MinerRow<n=2, resource=iron-ore>", "MinerRow<n=4, resource=iron-ore>"))

    def add_gears(self, n):
        shutil.copy(os.path.join(MERGE, "gears.fk"), os.path.join(self.dir, "stages", str(n)))
        self.write(f"stages/{n}/nauvis.surface", GEARS_PLACE, mode="a")

    def test_first_use_makes_main_from_game_beside_it(self):
        out = self.fk("list")
        self.assertIn("0 stages planned ahead of what is built", out)
        self.assertIn("60 plates/min", out)
        self.assertIn("horizon 1.00x", out)
        self.assertIn("below 1.5x: planning the next stages is the next job", out)
        self.assertTrue(os.path.isdir(os.path.join(self.dir, ".stage")))
        self.assertFalse([f for f in os.listdir(self.game) if f.startswith(".")])  # no sync sees it
        main = self.plan.ref("main")
        self.assertEqual(self.plan.ref("plan"), main)
        self.assertEqual(sorted(self.plan.ls(main)), ["iron.fk", "nauvis.build.fkb",
                                                      "nauvis.surface"])

    def test_main_holds_game_but_out(self):
        self.write("game/iron.fkp", "fkp 1 factory iron\n")
        self.write("game/out/report_checks.txt", "a report\n")
        self.fk("list")
        files = self.plan.ls(self.plan.ref("main"))
        self.assertIn("iron.fkp", files)
        self.assertFalse([f for f in files if f.startswith("out/")])

    def test_a_stage_is_one_commit_of_source_with_its_spec(self):
        out = self.fk("insert", "more smelting", "--goal", "8 furnaces", "--rates",
                      "iron-plate 120/min", "--test", "120 plates/min in fk stats")
        self.assertIn("stage 1 inserted, first: more smelting", out)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "stages", "1", "nauvis.build.fkb")))
        self.assertIn("no changes yet", self.fk("list"))
        self.more_smelting(1)
        self.write("stages/1/notes.json", "{}\n")                     # not source: stays out
        out = self.fk("edit", "1")
        self.assertIn("stage 1 now holds source iron.fk", out)
        self.assertIn("not taken (the plan holds .fk, .surface and .fkb files and the files "
                      "Literals read only): notes.json", out)
        st, = self.plan.stages()
        self.assertEqual((st.n, st.title), (1, "more smelting"))
        self.assertEqual(st.spec, {"goal": "8 furnaces", "rates": "iron-plate 120/min",
                                   "test": "120 plates/min in fk stats"})
        self.assertEqual(self.plan.changed(st.parent, st.commit, source=False), ["iron.fk"])
        body = self.git("log", "-1", "--format=%B", st.commit)
        self.assertTrue(body.startswith("stage 1: more smelting\n\ngoal: 8 furnaces\n"))
        self.assertIn("\nStage: 1\n", body)
        self.assertEqual(self.plan.revs(), [1])                      # the empty stage, kept
        out = self.fk("list")
        self.assertIn("stage 1  next  more smelting: 120 plates/min", out)
        self.assertIn("rates: iron-plate 120/min", out)
        self.assertIn("horizon 2.00x", out)
        self.assertIn("within 1.5-2x", out)
        self.assertEqual(self.fk("edit", "1", "--needs", "4 furnaces of stock").count("the spec"), 1)
        self.assertEqual(self.plan.stages()[0].spec["needs"], "4 furnaces of stock")

    def test_check_builds_the_stage_in_its_folder_and_never_the_world(self):
        self.fk("insert", "gears", "--rates", "iron-gear-wheel 30/min, iron-plate 999/min")
        self.add_gears(1)
        before = sorted(os.listdir(self.game))
        seen = []                                  # FK_LINK as each step of the build sees it
        steps = {k: (lambda f: lambda ctx, args: seen.append(os.environ.get("FK_LINK"))
                     or f(ctx, args))(f) for k, f in flow.STEPS.items()}
        with mock.patch.dict(os.environ, {"FK_LINK": "on"}), \
                mock.patch.dict(flow.STEPS, steps):
            out = self.fk("check", "1")
            self.assertEqual(os.environ["FK_LINK"], "on")
        self.assertEqual(set(seen), {None})
        self.assertIn("with its unsaved edits (gears.fk, nauvis.surface: fk stage edit 1 keeps "
                      "them)", out)
        self.assertRegex(out, r"steps to report_checks in \d+ s; check lines: ")
        self.assertIn("expected iron-gear-wheel 30/min: 38/min on paper", out)
        self.assertIn("expected iron-plate 999/min: 60/min on paper (EXPECT: short", out)
        self.assertIn("rates on paper: 60 plates/min (iron 60, copper 0), 60 before it", out)
        # the bill: what the gears add beyond the built base (main has no layout here), and that
        # nothing before the stage makes assemblers
        self.assertIn("+2 assembling-machine-1: no maker before it", out)
        self.assertEqual(sorted(os.listdir(self.game)), before)       # game\ untouched
        reports = os.path.join(self.dir, "stages", "1", "out")
        self.assertTrue(os.path.exists(os.path.join(reports, "report_checks.txt")))
        with open(os.path.join(reports, "stage-check.json"), encoding="utf-8") as fh:
            rec = json.load(fh)
        self.assertEqual(rec["counts"]["assembling-machine-1"], 2)
        self.assertIn("checked: changed since its check", self.fk("list"))  # the edits aren't in
        self.fk("edit", "1")
        self.fk("check", "1")
        self.assertRegex(self.fk("list"), r"stage 1  next  gears: 60 plates/min; checked: ")

    def test_check_draws_the_stage_and_knows_the_last_builds_stock(self):
        # the first lead run: a design worker wrote a script to read out\floorplan, since fk look
        # --design draws the committed layouts; and a bill in a copy had no stock to compare
        self.write("game/out/report_bom.txt",
                   "STOCK: robots can build 1 of 2 kinds now\n"
                   "  assembling-machine-1         need     2  network      3\n"
                   "  requester-chest              need     1  network      0  LOCKED\n")
        self.fk("insert", "gears")
        self.add_gears(1)
        out = self.fk("check", "1", "--render")
        self.assertIn("the design as this check laid it out, plot gears:", out)
        drawn = out.split("plot gears:\n", 1)[1].splitlines()[:16]
        self.assertEqual(len(drawn), 16)                       # the gears plot is 16x16
        self.assertTrue(all(len(line) == 16 for line in drawn), drawn)
        self.assertIn("+2 assembling-machine-1: no maker before it: from stock, the shop, or a "
                      "stage that makes it; the network held 3", out)
        self.assertIn("+1 requester-chest: no maker before it: from stock, the shop, or a stage "
                      "that makes it; the network held 0, LOCKED", out)
        self.assertIn("as game\\'s last build read it", out)
        self.assertIn("stages\\1\\out\\render.txt draws it", self.fk("check", "1"))
        self.assertIn("area 0,0,4,2:", self.fk("check", "1", "--render", "0,0,4,2"))

    def test_the_bill_counts_from_the_stage_before_it_and_names_its_makers(self):
        self.fk("insert", "gears")
        self.add_gears(1)
        self.fk("edit", "1")
        self.fk("check", "1")
        self.fk("insert", "more smelting")
        self.more_smelting(2)
        out = self.fk("check", "2")
        self.assertIn("bill: what it builds beyond stage 1 (its check)", out)
        self.assertIn("+4 stone-furnace: no maker before it", out)
        self.assertIn("rates on paper: 120 plates/min (iron 120, copper 0), 60 before it", out)
        self.assertIn("this stage reaches 2.00x the built base's plates", out)

    def test_next_apply_done(self):
        self.fk("insert", "gears", "--test", "gears in the box")
        self.add_gears(1)
        self.fk("edit", "1")
        self.fk("insert", "more smelting")
        self.more_smelting(2)
        self.fk("edit", "2")
        out = self.fk("next")
        self.assertIn("next: stage 1: gears", out)
        self.assertIn("+++ b/gears.fk", out)
        self.assertIn("+place gears = gears plot 22,0 16x16", out)
        self.assertFalse(os.path.exists(os.path.join(self.game, "gears.fk")))  # shown, not put
        out = self.fk("next", "--apply")
        self.assertIn("added game\\gears.fk", out)
        self.assertIn("wrote game\\nauvis.surface", out)
        self.assertIn(GEARS_PLACE, self.read("game/nauvis.surface"))
        self.write("game/out/apply.txt", "apply nauvis: 40 entities designed\n")
        self.write("game/gears.fkp", "fkp 1 factory gears\n")          # the build's layout
        out = self.fk("done", "-m", "the box fills")
        self.assertIn("done: stage 1: gears, now in main", out)
        self.assertIn("built as the plan has it", out)
        self.assertIn("the stage's test: gears in the box", out)
        self.assertIn("the plan: 1 stage ahead, replayed onto it cleanly, next stage 2", out)
        self.assertNotIn("note:", out)
        main = self.plan.ref("main")
        self.assertIn("gears.fkp", self.plan.ls(main))                 # a built layout lands
        body = self.git("log", "-1", "--format=%B", main)
        self.assertIn("built: built as the plan has it; the box fills", body)
        self.assertIn("Stage: 1", body)
        st, = self.plan.stages()
        self.assertEqual((st.n, st.parent), (2, main))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "stages", "1")))  # nothing its own
        self.assertIn("1 stage done, the last stage 1", self.fk("list"))

    def test_done_says_how_the_build_differs_and_what_looks_unbuilt(self):
        self.fk("insert", "more smelting")
        self.more_smelting(1)
        self.fk("edit", "1")
        self.fk("next", "--apply")
        self.write("game/iron.fk", self.read("game/iron.fk").replace("SmelterRow<n=8",
                                                                      "SmelterRow<n=7"))
        out = self.fk("done")
        self.assertIn("built differently from the plan in iron.fk", out)
        self.assertIn("no build has pasted in this game folder yet", out)
        self.assertIn("nothing planned, so planning is the next job", out)
        self.assertIn("SmelterRow<n=7", self.plan.show(self.plan.ref("main"), "iron.fk").decode())

    def test_reality_conflicts_with_a_stage_and_the_lead_settles_it(self):
        self.fk("insert", "more smelting")
        self.more_smelting(1)
        self.fk("edit", "1")
        self.fk("insert", "gears")
        self.add_gears(2)
        self.fk("edit", "2")
        # Rory adds a fifth furnace by hand, and the lead adopts it into game\
        self.write("game/iron.fk", self.read("game/iron.fk").replace("SmelterRow<n=4",
                                                                      "SmelterRow<n=5"))
        out = self.fk("rebase", "-m", "Rory's fifth furnace")
        self.assertIn("main takes game\\ as it stands", out)
        self.assertIn("stage 1: CONFLICT in iron.fk", out)
        self.assertNotIn("stage 2: CONFLICT", out)
        self.assertIn("Rory's fifth furnace", self.git("log", "-1", "--format=%B", "main"))
        text = self.plan.show(self.plan.stages()[0].commit, "iron.fk").decode()
        self.assertIn("<<<<<<< what is built\nsmelt = SmelterRow<n=5", text)
        self.assertIn("SmelterRow<n=8, recipe=iron-plate> @(8, 11)\n>>>>>>> stage 1\n", text)
        out = self.fk("list")
        self.assertIn("more smelting: CONFLICT in iron.fk; no rates", out)
        self.assertNotIn("unsaved edits", out)              # a stale folder has none of its own
        self.assertIn("stage 1 and after have no rates yet (more smelting)", out)
        self.assertIn("horizon 1.00x", out)
        # settle it in the folder: the plan's eight furnaces win
        self.fk("check", "1")
        path = "stages/1/iron.fk"
        self.write(path, re.sub(r"<<<<<<< [^\n]*\n.*?=======\n(.*?)>>>>>>> [^\n]*\n", r"\1",
                                self.read(path), flags=re.S))
        out = self.fk("edit", "1")
        self.assertIn("the 1 stage after it replayed cleanly", out)
        out = self.fk("list")
        self.assertNotIn("CONFLICT", out)
        self.assertIn("horizon 2.00x", out)

    def test_a_literals_file_travels_with_its_fk(self):
        # 2.0.4 (the lead-v2 run, 2026-10-22): stage 1 took relay.fk but not the relay.json its
        # Literal reads, so every check of the plan said "relay.fk Literal: No such file"
        self.fk("insert", "relay")
        self.write("stages/1/relay.fk", '# a relay\nport = Literal<file="relay.json"> @(0, 0)\n')
        self.write("stages/1/relay.json",
                   '[{"name": "small-electric-pole", "x": 0.5, "y": 0.5}]\n')
        self.write("stages/1/nauvis.surface", "place relay = relay plot 22,0 4x4\n", mode="a")
        out = self.fk("edit", "1")
        self.assertIn("stage 1 now holds source nauvis.surface, relay.fk, relay.json", out)
        self.assertNotIn("not taken", out)
        st, = self.plan.stages()
        self.assertIn("relay.json", self.plan.ls(st.commit))
        got = self.plan.measure(st.commit)
        self.assertEqual(got["errors"], [])
        self.assertEqual(got["plates"], 60.0)
        self.assertIn("+++ b/relay.json", self.fk("next"))
        self.assertIn("added game\\relay.json", self.fk("next", "--apply"))
        self.assertTrue(os.path.exists(os.path.join(self.game, "relay.json")))
        # an edit of the file alone is an edit of the stage
        self.fk("check", "1")
        self.write("stages/1/relay.json",
                   '[{"name": "small-electric-pole", "x": 1.5, "y": 0.5}]\n')
        self.assertIn("stages\\1 has unsaved edits (relay.json)", self.fk("list"))
        self.assertIn("stage 1 now holds source relay.json", self.fk("edit", "1"))

    def test_a_literals_file_reaches_the_stages_replayed_after_it(self):
        # 2.0.4 (the lead-v2 run, 11:39): stage 7's plant-40mw.json was not taken by edit, and
        # stages 3 and 5, replayed after it, stopped at elaborate with "No such file"
        self.fk("insert", "plant")
        self.fk("insert", "gears")
        self.add_gears(2)
        self.fk("edit", "2")
        self.fk("check", "2")                                 # stages\2 made before the plant
        self.write("stages/1/plant.fk", 'reactor = Literal<file="plant.json"> @(0, 0)\n')
        self.write("stages/1/plant.json",
                   '[{"name": "small-electric-pole", "x": 0.5, "y": 0.5}]\n')
        self.write("stages/1/nauvis.surface", "place plant = plant plot 40,0 4x4\n", mode="a")
        out = self.fk("edit", "1")
        self.assertIn("plant.json", out)
        self.assertIn("the 1 stage after it replayed cleanly", out)
        one, two = self.plan.stages()
        self.assertIn("plant.json", self.plan.ls(one.commit))
        self.assertIn("plant.json", self.plan.ls(two.commit))
        self.assertEqual(self.plan.measure(two.commit)["errors"], [])
        out = self.fk("check", "2")                           # the folder brought up to it
        self.assertNotIn("No such file", out)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "stages", "2", "plant.json")))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "stages", "2", "plant.fk")))

    def test_a_folders_own_edits_survive_a_plan_change(self):
        self.fk("insert", "more smelting")
        self.fk("insert", "gears")
        self.add_gears(2)                                    # unsaved in stages\2
        self.more_smelting(1)
        self.fk("edit", "1")                                 # stage 2's commit changes under it
        self.assertIn("stages\\2 has unsaved edits (gears.fk, nauvis.surface)", self.fk("list"))
        out = self.fk("check", "2")
        self.assertIn("stages\\2 brought up to the plan's stage 2, its own edits kept", out)
        self.assertIn("SmelterRow<n=8", self.read("stages/2/iron.fk"))         # the plan's
        self.assertTrue(os.path.exists(os.path.join(self.dir, "stages", "2", "gears.fk")))
        self.fk("edit", "2")
        self.assertEqual(self.plan.changed(self.plan.ref("main"), self.plan.ref("plan")),
                         ["gears.fk", "iron.fk", "nauvis.surface"])

    def test_insert_drop_reorder_keep_numbers_and_old_plans(self):
        for title in ("a", "b", "c"):
            self.fk("insert", title)
        self.fk("insert", "between", "--after", "1")
        self.assertEqual([s.n for s in self.plan.stages()], [1, 4, 2, 3])
        self.assertIn("the plan now: 3, 1, 4, 2", self.fk("reorder", "3", "--first"))
        self.fk("reorder", "1", "--after", "2")
        self.assertEqual([s.n for s in self.plan.stages()], [3, 4, 2, 1])
        out = self.fk("drop", "4")
        self.assertIn("dropped stage 4: between", out)
        self.assertEqual([s.n for s in self.plan.stages()], [3, 2, 1])
        self.fk("insert", "d")
        self.assertEqual(self.plan.stages()[-1].n, 5)           # a number is never used twice
        tags = self.git("tag", "-n1", "-l", "plan/rev-*")
        self.assertIn("before fk stage drop 4", tags)
        self.assertIn("before fk stage reorder 3", tags)
        main = self.plan.ref("main")
        self.assertTrue(all(s.tree == self.plan.tree(main) for s in self.plan.stages()))

    def test_the_loops_horizon_line(self):
        out = self.fk("horizon")
        self.assertIn("no plan yet", out)
        self.assertFalse(os.path.exists(os.path.join(self.dir, ".stage")))  # it makes none
        self.fk("insert", "more smelting")
        self.more_smelting(1)
        self.fk("edit", "1")
        out = self.fk("horizon").strip()
        self.assertEqual(len(out.splitlines()), 1)
        self.assertEqual(out, "the plan: 1 stage ahead, next stage 1: more smelting; horizon "
                         "2.00x: the plan reaches 120 plates/min, the built base 60 "
                         "(within 1.5-2x)")


class MeasureTest(unittest.TestCase):
    def test_the_horizon_words(self):
        self.assertIn("below 1.5x: planning the next stages is the next job",
                      stage.horizon_text(600, 700))
        self.assertIn("horizon 1.75x", stage.horizon_text(400, 700))
        self.assertIn("within 1.5-2x", stage.horizon_text(400, 700))
        self.assertIn("past 2x", stage.horizon_text(100, 700))
        self.assertIn("the built base makes no plates yet; the plan reaches 75",
                      stage.horizon_text(0, 75))

    def test_a_requester_chests_plates_are_made_elsewhere(self):
        cat = Catalog.load()
        got = stage.measure_flats({"gears": elaborate_file(os.path.join(MERGE, "gears.fk"), cat),
                                   "iron": elaborate_file(os.path.join(MERGE, "iron.fk"), cat)})
        self.assertEqual(got["plates"], 60.0)                 # the furnaces', not the robots'
        self.assertEqual(got["made"]["iron-gear-wheel"], 37.5)
        self.assertEqual(got["spm"], {})

    def test_a_message_round_trips(self):
        text = stage.message(7, "oil", {"needs": "oil-processing", "goal": "plastic"}, ["a note"])
        self.assertEqual(text, "stage 7: oil\n\ngoal: plastic\nneeds: oil-processing\na note\n\n"
                               "Stage: 7\n")
        self.assertEqual(stage.parse_message(text),
                         (7, "oil", {"goal": "plastic", "needs": "oil-processing"}, ["a note"]))


class CommandTest(unittest.TestCase):
    def test_fk_runs_stage_here_on_the_run_folder(self):
        sys.path.insert(0, os.path.join(ROOT, "agent"))
        try:
            import fk
        finally:
            sys.path.pop(0)
        calls = []
        with mock.patch.object(fk, "_config", lambda: {"host": "local"}), \
                mock.patch.object(fk, "local", lambda cfg, args: calls.append(args) or 0), \
                mock.patch.object(fk, "footer", lambda cfg: 0):
            self.assertEqual(fk.main(["stage", "check", "3"]), 0)
        self.assertEqual(calls, [["stage", ".", "check", "3"]])

    def test_fkcore_takes_the_stage_command(self):
        d = tempfile.mkdtemp(prefix="fkstage-cli-")
        self.addCleanup(shutil.rmtree, d, True)
        game = os.path.join(d, "game")
        os.makedirs(game)
        r = subprocess.run([sys.executable, "-m", "fkcore", "stage", game, "horizon"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no plan yet", r.stdout)


if __name__ == "__main__":
    unittest.main()
