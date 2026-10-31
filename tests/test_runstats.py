"""fkcore.runstats on fixture samples (no game): the deltas, the recorder file, the sampler's
choices, the history and the page; and the research line's rate (fkcore.supply)."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from fkcore import capital, link, runstats, supply

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN = os.path.join(HERE, "..", "scenario", "fk-play", "fk_stats.lua")
sys.path.insert(0, os.path.join(HERE, "..", "kickoff"))
import stats_sample  # noqa: E402


def raw(tick, made=None, used=None, power=None, seed=7, research=None, machines=None):
    """A sample as the Lua writes it (Lua's empty tables come back as lists)."""
    return {"tick": tick, "seed": seed, "force": "player", "surface": "nauvis",
            "items": {"made": made or [], "used": used or []},
            "fluids": {"made": {"water": tick / 10}, "used": []},
            "power": power or {"1": {"made": {"steam-engine": tick * 1000.0},
                                     "used": {"assembling-machine-2": tick * 600.0,
                                              "inserter": tick * 100.0}}},
            "research": research or {"researched": 5, "queue": 1, "name": "automation",
                                     "progress": tick / 300000, "units": 10,
                                     "ingredients": [["automation-science-pack", 1]]},
            "machines": machines or {"assembling-machine-2": {"working": 3,
                                                              "item_ingredient_shortage": 1}},
            "recipes": {"iron-gear-wheel": {"working": 3, "item_ingredient_shortage": 1}},
            "types": {"steam-engine": "generator", "assembling-machine-2": "assembling-machine",
                      "inserter": "inserter"}}


def items(tick):
    return {"iron-plate": tick // 10, "iron-gear-wheel": tick // 40}, \
        {"iron-plate": tick // 20, "automation-science-pack": tick // 600}


def sample_at(tick, **kw):
    made, used = items(tick)
    return runstats.norm(raw(tick, made, used, **kw), "rcon")


class SampleLuaTest(unittest.TestCase):
    def test_the_scenario_and_the_rcon_read_run_the_same_lua(self):
        with open(SCEN, encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r"-- fk_stats sample: begin[^\n]*\n(.*?)-- fk_stats sample: end", text, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), runstats.SAMPLE_LUA)

    def test_the_rcon_read_registers_nothing(self):
        lua = runstats.lua_sample("player", "nauvis", "stats-1")
        link.assert_safe(lua)
        link.assert_safe(runstats.lua_tick("nauvis"))
        self.assertIn("helpers.write_file('fk5/stats-1.json'", lua)
        self.assertNotIn("script.", link.lua_one_line(lua))
        self.assertNotIn("storage", lua)


class DeltaTest(unittest.TestCase):
    def test_the_first_sample_counts_from_the_map_start(self):
        out = dict(runstats.delta(None, sample_at(18000)))
        self.assertEqual(out["items"]["from"], 0)
        self.assertEqual(out["items"]["made"], {"iron-plate": 1800, "iron-gear-wheel": 450})
        self.assertEqual(out["power"]["made"], {"steam-engine": 18000000})
        self.assertEqual(out["power"]["types"]["inserter"], "inserter")
        self.assertEqual(out["research"]["packs"], {"automation-science-pack": 30})
        self.assertEqual(out["machines"]["machines"]["assembling-machine-2"]["working"], 3)

    def test_a_window_is_the_change_since_the_last_sample(self):
        out = dict(runstats.delta(sample_at(18000), sample_at(36000)))
        self.assertEqual((out["items"]["from"], out["items"]["tick"]), (18000, 36000))
        self.assertEqual(out["items"]["made"]["iron-plate"], 1800)
        self.assertEqual(out["items"]["used"]["automation-science-pack"], 30)
        self.assertEqual(out["fluids"]["made"], {"water": 1800})
        self.assertEqual(out["power"]["used"], {"assembling-machine-2": 10800000,
                                                "inserter": 1800000})

    def test_a_late_sample_is_one_long_window(self):
        out = dict(runstats.delta(sample_at(18000), sample_at(90000)))
        self.assertEqual(out["items"]["made"]["iron-plate"], 7200)
        self.assertEqual(out["items"]["from"], 18000)

    def test_counts_that_went_down_are_a_gap(self):
        out = runstats.delta(sample_at(36000), sample_at(54000, research=None))
        self.assertNotIn("gap", dict(out)["items"])
        back = sample_at(54000)
        back["items"]["made"]["iron-plate"] = 10
        out = dict(runstats.delta(sample_at(36000), back))
        self.assertIn("went down", out["items"]["gap"])
        self.assertIn("gap", out["power"])
        self.assertIn("machines", out["machines"])     # the states are a snapshot: kept

    def test_another_map_or_an_earlier_tick_is_a_gap(self):
        self.assertEqual(dict(runstats.delta(sample_at(36000), sample_at(54000, seed=8)))
                         ["items"]["gap"], "another map")
        self.assertIn("went back", dict(runstats.delta(sample_at(36000), sample_at(18000)))
                      ["fluids"]["gap"])

    def test_a_network_that_changed_starts_over(self):
        prev = sample_at(18000, power={"1": {"made": {"steam-engine": 5e9}, "used": []},
                                       "2": {"made": {"solar-panel": 1e6}, "used": []}})
        cur = sample_at(36000, power={"1": {"made": {"steam-engine": 1e9}, "used": []},
                                      "2": {"made": {"solar-panel": 3e6}, "used": []},
                                      "3": {"made": {"solar-panel": 5e5}, "used": []}})
        out = dict(runstats.delta(prev, cur))
        # network 1 went down (it changed): left out; 2 grew by 2 MJ; 3 is new: all of it
        self.assertEqual(out["power"]["made"], {"solar-panel": 2500000})


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "samples.jsonl")

    def tearDown(self):
        shutil.rmtree(self.dir, True)

    def write(self, rows, tail=""):
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            fh.write(tail)

    def test_reads_whole_lines_past_the_offset(self):
        self.write([{"tick": 18000, "seed": 1}, {"tick": 36000, "seed": 1}], '{"tick": 5')
        got, off = runstats.recorder(self.path, 0)
        self.assertEqual([g["tick"] for g in got], [18000, 36000])
        self.assertEqual(runstats.recorder(self.path, off), ([], off))
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write('4000, "seed": 1}\n')
        got, off2 = runstats.recorder(self.path, off)
        self.assertEqual([g["tick"] for g in got], [54000])
        self.assertEqual(off2, os.path.getsize(self.path))

    def test_a_file_that_shrank_is_read_from_its_start(self):
        self.write([{"tick": 18000, "seed": 1}])
        got, _off = runstats.recorder(self.path, 10 ** 6)
        self.assertEqual(len(got), 1)

    def test_the_first_read_takes_only_the_current_map(self):
        self.write([{"tick": 18000, "seed": 1}, {"tick": 36000, "seed": 1},
                    {"tick": 18000, "seed": 1}, {"tick": 36000, "seed": 1},
                    {"tick": 54000, "seed": 1}])
        got, _ = runstats.recorder(self.path, 0, first=True)
        self.assertEqual([g["tick"] for g in got], [18000, 36000, 54000])
        self.assertEqual(len(runstats.recorder(self.path, 0)[0]), 5)

    def test_no_file(self):
        self.assertEqual(runstats.recorder(self.path + ".none", 7), ([], 0))


class FakeRcon:
    """The game, as far as the sampler reads it: the tick and seed, and the RCON sample."""

    def __init__(self, out_dir, tick, seed=7):
        self.out, self.tick, self.seed, self.reads = out_dir, tick, seed, 0

    def lua(self, body):
        if "fk_stats_sample(f, s)" in body:
            self.reads += 1
            tag = re.search(r"fk5/(stats-\d+)\.json", body).group(1)
            made, used = items(self.tick)
            os.makedirs(os.path.join(self.out, "fk5"), exist_ok=True)
            with open(os.path.join(self.out, "fk5", f"{tag}.json"), "w") as fh:
                json.dump(raw(self.tick, made, used, seed=self.seed), fh)
            return "1"
        return f"{self.tick} {self.seed}"


class SampleTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.game, self.out = os.path.join(self.dir, "game"), os.path.join(self.dir, "so")
        os.makedirs(self.out)
        self.cap = mock.patch.object(capital, "run", return_value=["working capital 40%"])
        self.capital_run = self.cap.start()
        self.od = mock.patch.object(link, "OUT_DIR", self.out)
        self.od.start()

    def tearDown(self):
        self.cap.stop()
        self.od.stop()
        shutil.rmtree(self.dir, True)

    def run_at(self, r, now=False):
        return runstats.sample(r, self.game, None, "player", "nauvis", now=now)

    def test_without_a_recorder_it_reads_over_rcon_every_5_game_minutes(self):
        r = FakeRcon(self.out, 18000)
        lines = self.run_at(r)
        self.assertEqual(r.reads, 1)
        self.assertIn("1 sample kept from RCON", lines[0])
        self.assertEqual(lines[1], "working capital 40%")
        r.tick = 18000 + runstats.EVERY - 60
        self.assertIn("nothing new", self.run_at(r)[0])
        self.assertEqual(r.reads, 1)
        r.tick = 18000 + runstats.EVERY
        self.run_at(r)
        self.assertEqual(r.reads, 2)
        w = runstats.windows(runstats.Store(self.game).read("items"))
        self.assertEqual([(x["from"], x["tick"]) for x in w], [(0, 18000), (18000, 36000)])
        r.tick += 60
        self.run_at(r, now=True)               # --now: at once
        self.assertEqual(r.reads, 3)

    def test_the_capital_every_10_game_minutes(self):
        r = FakeRcon(self.out, 36000)
        with mock.patch.object(capital.Store, "history", return_value=[(18000, 1.0, 2.0)]):
            self.run_at(r)
            self.assertEqual(self.capital_run.call_count, 0)
            r.tick = 54000
            self.run_at(r)
            self.assertEqual(self.capital_run.call_count, 1)

    def test_with_a_live_recorder_it_reads_its_lines_and_not_rcon(self):
        path = os.path.join(self.out, "fk-stats")
        os.makedirs(path)
        with open(os.path.join(path, "samples.jsonl"), "w", encoding="utf-8") as fh:
            for t in (18000, 36000):
                made, used = items(t)
                fh.write(json.dumps(raw(t, made, used)) + "\n")
            made, used = items(18000)
            fh.write(json.dumps(raw(18000, made, used, seed=99)) + "\n")   # another map's
        r = FakeRcon(self.out, 36100)
        lines = self.run_at(r)
        self.assertEqual(r.reads, 0)
        self.assertIn("2 samples kept from the recorder", lines[0])
        r.tick = 36000 + runstats.EVERY + 100   # the recorder's next line is not read yet
        self.assertIn("recorder writes it", self.run_at(r)[0])
        self.assertEqual(r.reads, 0)
        r.tick = 36000 + runstats.EVERY + runstats.SLACK + 60     # the recorder stopped
        self.run_at(r)
        self.assertEqual(r.reads, 1)

    def test_next_due_for_the_loop(self):
        self.assertIsNone(stats_sample.next_due(self.dir))
        r = FakeRcon(self.out, 18000)
        self.run_at(r)
        self.assertEqual(stats_sample.next_due(self.dir), 18000 + runstats.EVERY)


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.game = os.path.join(self.dir, "run", "game")
        store, state = runstats.Store(self.game), {}
        rows = [sample_at(18000 * k) for k in range(1, 15)]
        rows.insert(6, runstats.norm(raw(30000, {"iron-plate": 1}, {}), "rcon"))   # a reset
        runstats.ingest(store, state, rows)
        store.save_state(state)
        os.makedirs(os.path.join(self.game, "out", "capital"))
        with open(os.path.join(self.game, "out", "capital", "history.jsonl"), "w") as fh:
            for k in range(1, 15):
                fh.write(json.dumps({"tick": 18000 * k, "working": 100.0 * k,
                                     "total": 1000.0 + 50 * k}) + "\n")

    def tearDown(self):
        shutil.rmtree(self.dir, True)

    def test_history_heads_with_research_then_window_and_trend(self):
        lines = runstats.history_lines(self.game)
        self.assertTrue(lines[0].startswith("research automation "), lines[0])
        self.assertIn("packs/min", lines[0])
        text = "\n".join(lines)
        self.assertIn("1 gap (resets)", text)
        self.assertIn("capital 1.7k raw units, 82% working (reinvested); an hour before", text)
        self.assertIn("made/min: iron-plate 360, iron-gear-wheel 90", text)
        self.assertIn("used/min: iron-plate 180, automation-science-pack 6.0", text)
        self.assertIn("power: made 60 kW, used 42 kW (balance +18 kW)", text)
        self.assertIn("made by steam engines 60 kW", text)
        self.assertIn("used by assemblers 36 kW, inserters 6 kW", text)
        self.assertIn("assembling-machine-2 3/4 working (1 short of input)", text)
        self.assertIn("trend, the last 30 min against the 52 before: iron-plate 418 -> 360/min",
                      text)    # the 52: one window runs from the reset to the next sample

    def test_no_samples(self):
        lines = runstats.history_lines(os.path.join(self.dir, "none"))
        self.assertEqual(lines[0], "research: no sample yet")
        self.assertIn("no samples yet", lines[1])

    def test_a_stalled_research_is_loud(self):
        store = runstats.Store(self.game)
        store.append("research", {"tick": 999999, "from": 999000, "name": "military-3",
                                  "progress": 0.34, "units": 100, "packs": {}})
        self.assertTrue(runstats.history_lines(self.game)[0].startswith("RESEARCH STALLED"))

    def test_the_page_plots_every_series(self):
        html = runstats.page(self.game)
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("<title>Run stats: run</title>", html)
        for name in ("iron-plate", "iron-gear-wheel", "automation-science-pack", "water",
                     "steam engines", "assemblers", "reinvestment", "iron-gear-wheel (made"):
            self.assertIn(name, html)
        self.assertIn("prefers-color-scheme: dark", html)
        self.assertGreater(html.count("<svg"), 10)
        path = runstats.write_page(self.game)
        self.assertTrue(path.endswith(os.path.join("out", "stats", "index.html")))

    def test_buckets_keep_the_totals(self):
        ws = [{"from": i * 10, "tick": (i + 1) * 10, "made": {"a": i}} for i in range(1000)]
        ws += [{"from": 20000, "tick": 20010, "made": {"a": 5}}]          # after a gap
        b = runstats._buckets(ws, 100)
        self.assertLessEqual(len(b), 101)
        self.assertEqual(sum(w["made"]["a"] for w in b), sum(range(1000)) + 5)
        self.assertEqual(b[-1], {"from": 20000, "tick": 20010, "made": {"a": 5}})


class ResearchLineTest(unittest.TestCase):
    def state(self, **kw):
        st = {"current": "military-3", "progress": 0.34, "queue": ["military-3", "laser"],
              "labs": 12, "tick": 500000, "units": 100, "labs_all": 12,
              "lab_states": {"working": 12},
              "ingredients": [{"name": p, "amount": 1, "held": 12, "min1": 10.25, "min10": 100}
                              for p in ("automation-science-pack", "logistic-science-pack",
                                        "military-science-pack", "chemical-science-pack")]}
        st.update(kw)
        return st

    def test_rate_and_time_left(self):
        # 41 packs/min of 4 a unit: 10.25 units/min, 66 units to go: ~6 min
        self.assertEqual(supply.research_line(self.state()),
                         "research military-3 34%, 41 packs/min, ~6 min left; queue: laser; "
                         "12 labs")

    def test_a_stall_names_the_pack_no_lab_holds(self):
        ing = self.state()["ingredients"]
        for i in ing:
            i["min1"] = 0
        ing[2]["held"] = 0
        line = supply.research_line(self.state(ingredients=ing, labs_all=0,
                                               lab_states={"missing_science_packs": 12}))
        self.assertTrue(line.startswith("RESEARCH STALLED: military-3 34%, 0 packs/min in the "
                                        "last minute: no lab holds military-science-pack"), line)

    def test_a_stall_where_no_lab_holds_all_packs(self):
        # the 20261030 run: military-3 at 0% with all 12 labs short, no lab holding all four
        ing = self.state()["ingredients"]
        for k, i in enumerate(ing):
            i["min1"], i["held"] = 0, 12 - 3 * k
        line = supply.research_line(self.state(ingredients=ing, labs_all=0))
        self.assertIn("no lab holds all 4 packs (chemical-science-pack missing in 9 of 12 labs)",
                      line)

    def test_a_stall_without_power(self):
        ing = self.state()["ingredients"]
        for i in ing:
            i["min1"] = 0
        line = supply.research_line(self.state(ingredients=ing, lab_states={"no_power": 12}))
        self.assertIn("the 12 labs have no power", line)

    def test_the_first_game_minute_is_not_a_stall(self):
        ing = self.state()["ingredients"]
        for i in ing:
            i["min1"] = 0
        line = supply.research_line(self.state(ingredients=ing, tick=1200))
        self.assertTrue(line.startswith("research military-3 34%, 0 packs/min"), line)

    def test_an_older_read_keeps_the_old_line(self):
        self.assertEqual(supply.research_line({"current": "automation", "progress": 0.45,
                                               "labs": 2}), "research: automation 45%; 2 labs")


if __name__ == "__main__":
    unittest.main()
