"""2.1.2, the small fixes from the runs (review of 2026-10-31): read-terrain merges an area into
the file, a stop_on word matches a check whether it is written with dashes or underscores, and
the template stops on cannot-carry."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import __main__ as cli
from fkcore import flow, terrain
from fkcore.elaborate import Check

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE = os.path.join(ROOT, "kickoff", "template", "game", "nauvis.build.fkb")


def block(area, water=(), resources=None, tick=7):
    return {"tick": tick, "area": list(area), "water": [list(t) for t in water], "other": [],
            "tiles": {"water": len(water)} if water else [], "resources": resources or [],
            "removable": [], "cliffs": [], "enemies": [], "ungenerated": []}


class TerrainMergeTest(unittest.TestCase):
    """10-29 run: ``fk read-terrain --area`` of the north copper replaced the whole base's
    terrain with that one area."""

    BASE = terrain.merge("nauvis", (-10, -10, 10, 10), [block(
        (-10, -10, 10, 10), water=[(-5, -5), (5, 5)],
        resources={"iron-ore": [[0, 0, 500], [1, 0, 600]]})])

    def test_an_area_reads_into_the_file(self):
        north = terrain.merge("nauvis", (-10, -40, 10, -20), [block(
            (-10, -40, 10, -20), water=[(0, -30)], resources={"copper-ore": [[2, -25, 900]]},
            tick=99)])
        got = terrain.combine(self.BASE, north)
        self.assertEqual(got.area, (-10, -40, 10, 10))
        self.assertEqual(got.water, frozenset({(-5, -5), (5, 5), (0, -30)}))
        self.assertEqual(got.resources["iron-ore"], {(0, 0): 500, (1, 0): 600})
        self.assertEqual(got.resources["copper-ore"], {(2, -25): 900})
        self.assertEqual(got.tick, 99)
        self.assertEqual(got.tiles, {"water": 3})          # apart: the counts add up

    def test_inside_the_new_area_the_new_read_wins(self):
        again = terrain.merge("nauvis", (0, 0, 10, 10), [block(
            (0, 0, 10, 10), resources={"iron-ore": [[0, 0, 450]]})])     # (1,0) mined out, (5,5) filled
        got = terrain.combine(self.BASE, again)
        self.assertEqual(got.area, (-10, -10, 10, 10))
        self.assertEqual(got.water, frozenset({(-5, -5)}))
        self.assertEqual(got.resources["iron-ore"], {(0, 0): 450})

    def test_the_command_merges_and_replace_replaces(self):
        folder = tempfile.mkdtemp(prefix="fkterrain-merge-")
        try:
            terrain.save(self.BASE, os.path.join(folder, "map.terrain.json"))
            north = terrain.merge("nauvis", (-10, -40, 10, -20),
                                  [block((-10, -40, 10, -20), water=[(0, -30)])]).to_dict()

            class Rcon:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            def run(*extra):
                with mock.patch.dict(os.environ, {"FK_LINK": "on"}), \
                        mock.patch("fkcore.link.Rcon", Rcon), \
                        mock.patch("fkcore.terrain.read", return_value=north), \
                        contextlib.redirect_stdout(io.StringIO()) as out:
                    code = cli.main(["read-terrain", folder, "--surface", "nauvis",
                                     "--area=-10,-40,10,-20", *extra])
                self.assertEqual(code, 0)
                with open(os.path.join(folder, "map.terrain.json"), encoding="utf-8") as fh:
                    return json.load(fh), out.getvalue()

            d, text = run()
            self.assertEqual(d["area"], [-10, -40, 10, 10])
            self.assertEqual(d["water"], [[0, -30], [-5, -5], [5, 5]])
            self.assertIn("merged into the old -10,-10,10,10", text)
            d, _text = run("--replace")
            self.assertEqual(d["area"], [-10, -40, 10, -20])
            self.assertEqual(d["water"], [[0, -30]])
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class StopOnTest(unittest.TestCase):
    def ctx(self, *words):
        c = flow.Ctx(".", "x.fkb", None, ".")
        c.stop_on |= {flow._stop_code(w) for w in words}
        return c

    def test_no_power_holds_the_paste_either_way_it_is_written(self):
        # 10-30 run: a steel row stood unpowered, and the paste went in anyway
        checks = [Check("NO_POWER", "main st_sm/f1", "all 25 spots are taken")]
        for word in ("NO_POWER", "no_power", "no-power"):
            with self.subTest(word=word):
                self.assertEqual(flow._stopping(self.ctx(word), checks), checks)
        self.assertEqual(flow._stopping(self.ctx("no-route"), checks), [])

    def test_a_dash_word_still_matches_a_dash_check(self):
        checks = [Check("cannot-carry", "net cu", "consumer mp takes no copper-plate")]
        self.assertEqual(flow._stopping(self.ctx("cannot_carry"), checks), checks)
        self.assertEqual(flow._stopping(self.ctx("cannot-carry"), checks), checks)

    def test_the_template_stops_on_cannot_carry(self):
        # 10-29 run: the pole maker on the copper-plate net was left off its route, unfed an hour
        with open(TEMPLATE, encoding="utf-8") as fh:
            lines = flow.parse(fh.read(), TEMPLATE)
        self.assertIn("cannot-carry", {a for ln in lines if ln.cmd == "stop_on" for a in ln.args})


class CaptureTest(unittest.TestCase):
    def test_only_what_stands_in_the_slot(self):
        # 10-31: `fk capture lab u0` took a drill of the next slot, whose box reached over the edge
        from fkcore import capture, link
        lua = capture.lua_capture("lab", "lab", (0, 0, 20, 20), "t")
        link.assert_safe(lua)
        self.assertIn("inside(src[b.entity_number])", lua)
        self.assertIn("p.x >= 0 and p.x < 20 and p.y >= 0 and p.y < 20", lua)


class RequestTest(unittest.TestCase):
    """fk request ENTITY ITEM N: an item-request proxy (the game's own), so robots bring items to
    an entity that stands. The players wrote robots.lua, ammo.lua and u0proxy.lua for it."""

    def test_a_minus_position_is_no_option(self):
        self.assertEqual(cli._glue(["request", "g", "-30.5,74", "piercing-rounds-magazine", "10",
                                    "--name", "gun-turret"]),
                         ["request", "--name", "gun-turret", "--", "g", "-30.5,74",
                          "piercing-rounds-magazine", "10"])

    def test_the_lua_only_asks(self):
        from fkcore import link
        lua = link.lua_request("nauvis", "player", (-30.5, 74), "construction-robot", 10)
        link.assert_safe(lua)
        self.assertIn("name = 'item-request-proxy'", lua)
        for word in (".insert{", ".insert(", "remove_item", ".set_stack", "transfer_stack",
                     "clear_items", "destroy"):
            self.assertNotIn(word, lua)

    def test_no_item_no_request(self):
        with mock.patch.dict(os.environ, {"FK_LINK": "on"}), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            code = cli.main(["request", ".", "1,1", "no-such-thing", "3"])
        self.assertEqual(code, 2)
        self.assertIn("no item no-such-thing", err.getvalue())

    def test_the_players_fk_sends_it_to_the_host(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_fk", os.path.join(ROOT, "agent",
                                                                              "fk.py"))
        fk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fk)
        self.assertIn("request", fk.HOST)


class StandingRoboportsTest(unittest.TestCase):
    def test_the_diff_keeps_them_for_the_next_cover_step(self):
        folder = tempfile.mkdtemp(prefix="fkstanding-")
        try:
            ctx = flow.Ctx(folder, "x.fkb", None, folder)
            ctx.surface = mock.Mock(name="surface")
            self.assertIsNone(flow._standing_roboports(ctx))
            rep = mock.Mock(verdicts=[])
            flow._save_standing(ctx, rep, [(8.0, 8.0, 25.0, 55.0)])
            self.assertEqual(flow._standing_roboports(ctx), [(8.0, 8.0, 25.0, 55.0)])
            flow._save_standing(ctx, rep)                    # a diff that read none keeps them
            self.assertEqual(flow._standing_roboports(ctx), [(8.0, 8.0, 25.0, 55.0)])
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class DryRunTest(unittest.TestCase):
    """10-31 run: "a dry run (`--to report_bom`) saves its routes to world.fkp". The template runs
    write_layout after report_bom; a build that stops at report_bom must leave every .fkp as it
    was, in the flow and through the player's fk (design here, game steps on the host)."""

    @classmethod
    def setUpClass(cls):
        cls.run_dir = tempfile.mkdtemp(prefix="fkdry-")
        game = os.path.join(cls.run_dir, "game")
        shutil.copytree(os.path.join(ROOT, "games", "nauvis"), game)
        with open(os.path.join(game, "nauvis.build.fkb"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        out = []
        for line in lines:                 # the template's order: diff, report_bom, write_layout
            if line.startswith(("report_bom", "write_layout")):
                continue
            out.append(line)
            if line.startswith("diff"):
                out += ["report_bom      --stock live", "write_layout"]
        with open(os.path.join(game, "nauvis.build.fkb"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write("\n".join(out) + "\n")
        with open(os.path.join(game, "main.fk"), encoding="utf-8") as fh:
            src = fh.read()
        moved = src.replace("recipe=inserter>                 @(58, 22)",
                            "recipe=inserter>                 @(60, 22)")
        assert moved != src
        with open(os.path.join(game, "main.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(moved)
        cls.game = game

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.run_dir, ignore_errors=True)

    def fkps(self):
        out = {}
        for name in sorted(os.listdir(self.game)):
            if name.endswith(".fkp"):
                with open(os.path.join(self.game, name), "rb") as fh:
                    out[name] = fh.read()
        return out

    def test_the_flow_writes_no_fkp(self):
        before = self.fkps()
        with mock.patch.dict(os.environ, {"FK_LINK": "off"}):
            code, ctx = flow.run(os.path.join(self.game, "nauvis.build.fkb"), to="report_bom",
                                 echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        self.assertIn("route", ctx.steps)
        self.assertEqual(self.fkps(), before)

    def test_the_players_fk_writes_no_fkp(self):
        import subprocess
        import sys
        os.makedirs(os.path.join(self.run_dir, "bin"), exist_ok=True)
        shutil.copy(os.path.join(ROOT, "agent", "fk.py"), os.path.join(self.run_dir, "bin"))
        tk = os.path.join(self.run_dir, ".toolkit")
        if not os.path.isdir(tk):
            shutil.copytree(os.path.join(ROOT, "fkcore"), os.path.join(tk, "fkcore"),
                            ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(self.run_dir, "run.json"), "w", encoding="utf-8") as fh:
            json.dump({"host": "local", "env": {"FK_RCON_PW_FILE": os.path.join(
                self.run_dir, "no-rcon.pw")}}, fh)
        before = self.fkps()
        env = {k: v for k, v in os.environ.items() if k not in ("FK_RUN", "FK_LINK")}
        r = subprocess.run([sys.executable, os.path.join(self.run_dir, "bin", "fk.py"), "build",
                            "--to", "report_bom"], cwd=self.run_dir, env=env,
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
        self.assertIn("report_bom", r.stdout)
        self.assertEqual(self.fkps(), before)


if __name__ == "__main__":
    unittest.main()
