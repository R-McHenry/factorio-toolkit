import json
import os
import re
import shutil
import tempfile
import unittest

from fkcore import compose, connect, fkp, flow, look, scene
from fkcore.catalog import Catalog
from fkcore.elaborate import ADVICE, elaborate_file

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "redgreen")
SOURCES = ("main.fk", "nauvis.surface", "nauvis.build.fkb")

#: 2.0.4 A2: a game codebase the size of the live run's shop: one crafter into a provider chest,
#: the shape of the shop.fkp whose old recipe the stale checkpoints kept. The surface is mall and
#: the module shop, so the factory checkpoint (out/<step>/gear.fkp) and the committed .fkp
#: (shop.fkp) are different files, as in the run.
SHOP_FK = """\
fein = Chest<requester, item=iron-plate, rate=1/s> @(0, 5)
gear = Assembler<recipe=iron-gear-wheel>          @(2, 0)
gb   = Chest<provider>                            @(8, 0)
net in:  fein -> gear
net out: gear -> gb
"""
SHOP_SURFACE = """\
surface  mall
mode     lab
terrain  none
catalog  base
place gear = shop plot 0,0 30x20
"""
#: the live run's script order: diff and report_bom before write_layout, robots before power, so
#: a host `--from diff` (the reported failure) runs write_layout after the layout steps.
SHOP_SCRIPT = """\
read_surface    mall
read_terrain    none
elaborate
size
place           --keep pinned
route           --only stale --effort normal
tier            minimize
cover robots
cover power     --pole medium-electric-pole
floorplan
report_checks
diff --scope stale
report_bom      --stock none
write_layout
apply           --scope stale
stop_on         invariant
"""


class FlowTest(unittest.TestCase):
    """CORE-V1 step 5: the red-green part of main builds through the default script."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkflow-")
        for name in SOURCES:
            shutil.copy(os.path.join(GAME, name), self.dir)
        self.script = os.path.join(self.dir, "nauvis.build.fkb")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self, frm=None, to=None):
        return flow.run(self.script, frm, to, CAT, echo=lambda _line: None)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def shop(self, fk=None):
        """The A2 game codebase under self.dir/shop, written from scratch."""
        folder = os.path.join(self.dir, "shop")
        os.makedirs(folder, exist_ok=True)
        for name, text in (("shop.fk", fk or SHOP_FK), ("mall.surface", SHOP_SURFACE),
                           ("mall.build.fkb", SHOP_SCRIPT)):
            with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        return folder

    def shop_build(self, folder, frm=None, to=None, said=None):
        return flow.run(os.path.join(folder, "mall.build.fkb"), frm, to, CAT,
                        echo=said.append if said is not None else (lambda _line: None))

    def shop_change(self, folder, old, new):
        path = os.path.join(folder, "shop.fk")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(old, text)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace(old, new))

    def shop_recipe(self, folder, *parts):
        """The recipe of the shop's one crafter in a factory checkpoint or the committed .fkp."""
        lay = fkp.load(os.path.join(folder, *parts))
        return sorted({e.attrs.get("recipe") for e in lay.entities.values()
                       if e.key.startswith("gear/") and e.attrs.get("recipe")})

    def shop_read(self, folder, *parts):
        with open(os.path.join(folder, *parts), encoding="utf-8") as fh:
            return fh.read()

    def test_the_default_script_builds_redgreen(self):
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        self.assertEqual(len(ctx.log), 20)
        # this surface has no power plant (games/nauvis has one), and main makes the transport
        # belts its routes are built from: BOOTSTRAP names them, one line per net they feed
        self.assertEqual([(s, c.code, c.where) for s, c in ctx.checks if c.code not in ADVICE],
                         [("floorplan", "NO_POWER", "nauvis main"),
                          ("report_checks", "bootstrap", "net main/iron"),
                          ("report_checks", "bootstrap", "net main/gear"),
                          # 2.0.15: its route needs plain inserters, and the only maker of one
                          # (main/ins) is fed by this same net
                          ("report_checks", "bootstrap", "net main/circ")])
        lay = fkp.load(os.path.join(self.dir, "main.fkp"))
        flat = elaborate_file(os.path.join(self.dir, "main.fk"), CAT)
        self.assertEqual(fkp.invariants(lay, CAT, nets=flat.nets), [])
        rep = connect.connect(lay, CAT, connect.endpoints(flat))
        self.assertEqual({r.status for r in rep.nets.values()}, {"connected"})
        self.assertEqual((len(rep.nets), rep.leaks), (12, []))
        self.assertIn("power", lay.covers)
        self.assertIn("185/185 electric entities covered; 1 wire component",
                      self.read("out/cover_power.txt"))
        for step in ("place", "route", "cover_power", "cover_robots", "floorplan"):
            self.assertTrue(os.path.exists(os.path.join(self.dir, "out", step, "main.fkp")), step)
        surface = fkp.load(os.path.join(self.dir, "nauvis.fkp"))
        s = compose.compose(surface, {"main": lay}, CAT)
        self.assertEqual(s.problems, [])
        self.assertIn("tier minimize (allowed: yellow)", self.read("out/tier.txt"))  # the default
        self.assertIn("; 0 changed", self.read("out/tier.txt"))
        rates_txt = self.read("out/report_rates.txt")      # both runs: before place, after route
        self.assertIn("# report_rates", rates_txt.split("routed main")[0])
        self.assertEqual(rates_txt.count("# report_rates"), 2)
        self.assertIn("target automation-science-pack 10/min: met", rates_txt)
        self.assertIn("routed main (V2: the lanes and inserters as laid)", rates_txt)
        self.assertIn("/min routed", rates_txt)
        self.assertIn("inserter hands 1 (no game link", rates_txt)

    def test_a_second_build_pins_everything(self):
        self.build()
        first = self.read("main.fkp")
        code, ctx = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(self.read("main.fkp"), first)
        self.assertIn("14 unchanged", self.read("out/place.txt"))
        self.assertIn("0 routed, 12 kept (12 pinned from the committed .fkp)",
                      self.read("out/route.txt"))

    def test_a_moved_row_reroutes_only_what_it_touches(self):
        self.build()
        path = os.path.join(self.dir, "main.fk")
        src = self.read("main.fk").replace("@(16, 45)", "@(16, 47)")       # labs, 2 tiles down
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        self.assertIn("labs: stale", self.read("out/place.txt"))
        route_txt = self.read("out/route.txt")
        self.assertIn("routed    packs:", route_txt)
        kept = int(re.search(r"(\d+) kept", route_txt).group(1))
        self.assertGreaterEqual(kept, 10)                     # the rest stay where they were
        self.assertIn("12 nets: 12 connected, 0 open, 0 unrouted; 0 SPILL",
                      self.read("out/report_checks.txt"))

    def test_a_moved_row_keeps_the_poles_that_stand(self):
        # 1.7 (Rory, 2026-10-21: pin and patch): a rebuild keeps the committed poles where they
        # still fit, so the grid that stands is not re-laid; cover power --fresh lays it anew
        def poles():
            lay = fkp.load(os.path.join(self.dir, "main.fkp"))
            return {(e.key, e.x, e.y) for e in lay.entities.values() if e.owner == "power"}

        self.build()
        first = poles()
        src = self.read("main.fk").replace("@(16, 45)", "@(16, 47)")       # labs, 2 down
        with open(os.path.join(self.dir, "main.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        self.assertIn("40 poles (37 kept where they stand, 0 bridging, 0 existing); 185/185",
                      self.read("out/cover_power.txt"))
        self.assertEqual(len(first & poles()), 37)
        script = self.read("nauvis.build.fkb").replace("cover power", "cover power --fresh")
        with open(self.script, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(script)
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        self.assertNotIn("kept where they stand", self.read("out/cover_power.txt"))
        self.assertLess(len(first & poles()), 37)

    def test_from_and_to_use_the_checkpoints(self):
        self.build(to="tier")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "main.fkp")))
        code, ctx = self.build(frm="cover_power", to="report_checks")
        self.assertEqual(code, 0)
        self.assertEqual([l.split("]")[0] for l in ctx.log],
                         ["[12/20", "[13/20", "[14/20", "[15/20"])
        self.assertIn("12 connected", self.read("out/report_checks.txt"))

    def test_a_step_run_twice_reports_its_checks_once(self):
        # 1.4.1 (lead review): the second report_rates repeated the ASSERT and TARGET lines
        path = os.path.join(self.dir, "nauvis.surface")
        text = self.read("nauvis.surface")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace("automation-science-pack 10/min",
                                  "automation-science-pack 1000/min"))
        code, ctx = self.build(to="report_rates:2")
        self.assertEqual(code, 0, ctx.log)
        self.assertEqual([s for s, c in ctx.checks if c.code == "target-not-met"], ["report_rates"])
        self.assertEqual(self.read("out/report_rates.txt").count("NOT met"), 2)
        code, ctx = self.build(frm="report_rates:2", to="report_rates:2")
        self.assertEqual(code, 0, ctx.log)
        self.assertEqual([l.split("]")[0] for l in ctx.log], ["[11/20"])     # the second one
        self.assertEqual(self.read("out/report_rates.txt").count("# report_rates"), 1)

    def test_a_bad_number_is_a_script_error(self):
        for line, why in (("tier minimize --red x", "--red needs a whole number"),
                          ("tier minimize --red", "--red needs a number"),
                          ("tier minimize --allow pink", "unknown tier pink"),
                          ("report_rates --hand two", "--hand needs a whole number"),
                          ("report_rates --hand 0", "--hand is at least 1")):
            with open(self.script, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("read_surface nauvis\nread_terrain none\nelaborate\nplace\n" + line + "\n")
            with self.assertRaises(flow.FlowError, msg=line) as caught:
                self.build()
            self.assertIn(why, str(caught.exception))
        with self.assertRaises(flow.FlowError):
            self.build(to="report_rates:2")

    def test_from_diff_replays_the_floorplan(self):
        # the laptop lays out (--to write_layout); the game host applies (--from diff)
        self.build(to="write_layout")
        code, ctx = self.build(frm="diff")
        self.assertEqual(code, 0, ctx.log)
        self.assertIsNotNone(ctx.composed)
        self.assertEqual(len(ctx.composed.entities), 1014)    # 974 + the 40 poles of cover power
        self.assertIn("skipped, no game link", self.read("out/diff.txt"))
        self.assertIn("skipped, no game link", self.read("out/apply.txt"))

    def test_a_resume_after_a_recipe_change_lays_out_again(self):
        # 2.0.4 A2 (the second lead run, 2026-10-22): a recipe changed in the source, a build
        # resumed on the old out/<step>/ checkpoints, write_layout wrote the old recipe into the
        # .fkp, the paste laid it, and `fk look` judged against that .fkp and said OK.
        folder = self.shop()
        code, ctx = self.shop_build(folder, to="write_layout")
        self.assertEqual(code, 0, ctx.log)
        old = ctx.composed
        self.assertEqual(self.shop_recipe(folder, "out", "cover_power", "gear.fkp"),
                         ["iron-gear-wheel"])
        self.shop_change(folder, "recipe=iron-gear-wheel>", "recipe=iron-stick>")
        said = []
        code, ctx = self.shop_build(folder, "diff", "write_layout", said)
        self.assertEqual(code, 0, ctx.log)
        self.assertIn("out/cover_power was laid from other source (shop.fk changed)", said[0])
        self.assertIn("shop.fk changed", self.shop_read(folder, "out", "diff.txt"))
        # every checkpoint is laid from the new source, not just the one the resume loaded
        for step in ("place", "route", "tier", "cover_power", "cover_robots", "floorplan"):
            self.assertEqual(self.shop_recipe(folder, "out", step, "gear.fkp"),
                             ["iron-stick"], step)
        self.assertEqual(self.shop_recipe(folder, "shop.fkp"), ["iron-stick"])
        self.assertEqual(flow.layout_source_changes(folder), [])
        # the look before the paste: the new .fkp against the game as the old build left it is a
        # recipe DRIFT, not the OK the stale .fkp gave
        sf, _surface_lay, _path, new = look.composed(folder, CAT)
        area = look.default_area(new, CAT)
        lk = look.report(new, scene.design_scene(old, CAT, area), CAT, area, look.policy(sf))
        self.assertEqual((lk.ok, lk.designed), (9, 10))
        self.assertEqual([(v.verdict, v.detail) for v in lk.rep.verdicts if v.verdict != "ok"],
                         [("settings-changed", "recipe iron-gear-wheel, designed iron-stick")])
        self.assertIn("settings-changed", "\n".join(lk.lines()))
        self.assertIn("designed iron-stick", "\n".join(lk.lines()))
        # the same source again: the checkpoints are taken as they stand, nothing is laid again
        said = []
        code, ctx = self.shop_build(folder, "diff", "write_layout", said)
        self.assertEqual(code, 0, ctx.log)
        self.assertEqual([line.split("]")[0] for line in said], ["[12/16", "[13/16", "[14/16"])
        # a look also says when the source moved on from the .fkp (until the next build writes it)
        with open(os.path.join(folder, "shop.fk"), "a", encoding="utf-8", newline="\n") as fh:
            fh.write("# an edit not built yet\n")
        self.assertEqual(len(flow.layout_source_changes(folder)), 1)
        self.assertIn("shop.fk changed since shop.fkp",
                      flow.layout_source_changes(folder)[0])

    def test_a_resume_after_a_guard_change_lays_out_again(self):
        # 2.0.4 A2: a guard change is a source change too. The circuits are laid at
        # floorplan, so out/floorplan/<factory>.fkp (what a later `--from` build or a look
        # reads) must be written again, not left as the previous build wrote it.
        folder = self.shop()
        code, ctx = self.shop_build(folder, to="write_layout")
        self.assertEqual(code, 0, ctx.log)
        before = fkp.load(os.path.join(folder, "out", "floorplan", "gear.fkp"))
        self.assertFalse(any(a in e.attrs for e in before.entities.values()
                             for a in ("if", "read", "filter")))
        self.shop_change(folder, "recipe=iron-gear-wheel>",
                         "recipe=iron-gear-wheel, guard>")
        said = []
        code, ctx = self.shop_build(folder, "diff", "write_layout", said)
        self.assertEqual(code, 0, ctx.log)
        self.assertIn("shop.fk changed", said[0])
        for parts in (("out", "floorplan", "gear.fkp"), ("shop.fkp",)):
            lay = fkp.load(os.path.join(folder, *parts))
            attrs = {e.key: e.attrs for e in lay.entities.values()}
            self.assertEqual(attrs["gear/m0"].get("read"), "ingredients", parts)
            self.assertEqual(attrs["~in/i1"].get("filter"), "circuit", parts)
        self.assertEqual(flow.layout_source_changes(folder), [])

    def test_a_checkpoint_with_no_source_stamp_is_stale(self):
        # 2.0.4 A2: the live run's checkpoints were written before the stamp existed. A build
        # must not take one as current: it is laid out again (the first build after the upgrade
        # would otherwise write and paste the old design again).
        folder = self.shop()
        code, ctx = self.shop_build(folder, to="write_layout")
        self.assertEqual(code, 0, ctx.log)
        self.shop_change(folder, "recipe=iron-gear-wheel>", "recipe=iron-stick>")
        os.remove(os.path.join(folder, "out", "cover_power", "source.json"))
        said = []
        code, ctx = self.shop_build(folder, "diff", "write_layout", said)
        self.assertEqual(code, 0, ctx.log)
        self.assertIn("it does not say what source it was laid from", said[0])
        for step in ("place", "route", "tier", "cover_power", "cover_robots", "floorplan"):
            self.assertEqual(self.shop_recipe(folder, "out", step, "gear.fkp"),
                             ["iron-stick"], step)
        with open(os.path.join(folder, "out", "cover_power", "source.json"),
                  encoding="utf-8") as fh:
            stamp = json.load(fh)
        self.assertEqual(stamp["files"]["shop.fk"],
                         flow._source_files(folder)["shop.fk"])

    def test_stop_on_stops_on_a_check(self):
        src = self.read("main.fk").replace("net cable:  cable -> circ\n", "")
        with open(os.path.join(self.dir, "main.fk"), "w", encoding="utf-8") as fh:
            fh.write(src)
        code, ctx = self.build()                              # UNFED is a warning by default
        self.assertEqual(code, 0)
        self.assertTrue(any(c.code == "no-feed" for _s, c in ctx.checks))
        with open(self.script, "a", encoding="utf-8") as fh:
            fh.write("stop_on no-feed\n")
        self.assertIn("routed    belt", self.read("out/route.txt"))
        self.assertIn("stop_on malformed: a check of these stops the run; none has stopped it so "
                      "far", self.read("out/stop_on.txt"))
        code, ctx = self.build()
        self.assertEqual(code, 1)
        self.assertTrue(ctx.log[-1].startswith("[ 4/21] elaborate"))   # 20 steps + stop_on
        # the steps it didn't reach say so, not the last run's lines (2026-10-21)
        route = self.read("out/route.txt")
        self.assertIn("not run: the build stopped at line", route)
        self.assertIn("(elaborate): ", route)
        self.assertNotIn("routed    belt", route)

    def test_the_machines_a_paste_takes_up(self):
        # the first lead run (2026-10-21): a paste took up the burner row while the belts its
        # replacement needed were SHORT, and iron stood still; report_bom warns from these
        from fkcore.sense import Verdict

        class Rep:
            verdicts = [Verdict("unowned", "burner-mining-drill", 1, 1),
                        Verdict("unowned", "assembling-machine-1", 5.5, 5.5, ghost=True),
                        Verdict("unowned", "transport-belt", 2.5, 2.5),
                        Verdict("other-entity", "transport-belt", 9.5, 9.5,
                                under=[("stone-furnace", 9, 9, None, False, True)]),
                        Verdict("ok", "electric-mining-drill", 20.5, 20.5)]
        ctx = flow.Ctx(self.dir, self.script, CAT, os.path.join(self.dir, "out"))
        self.assertEqual(flow._machines_taken_up(ctx), [])
        ctx.last_diff = Rep
        self.assertEqual(flow._machines_taken_up(ctx), ["burner-mining-drill", "stone-furnace"])

    def test_what_no_powered_roboport_reaches_is_said_before_the_paste(self):
        # 2.0.1 (the first lead run's plates worker): a power bridge through ground no powered
        # roboport reached, and the relay roboport that would have reached it was powered only
        # through that bridge: its poles stood as ghosts for ever
        from fkcore.sense import Verdict

        class Rep:
            verdicts = [Verdict("ghost", "medium-electric-pole", 63.5, 34.5, "nauvis:bridge/p0"),
                        Verdict("not-placed", "roboport", 100, 100, "nauvis:out/robots/r0"),
                        Verdict("not-placed", "assembling-machine-1", 130.5, 100.5, "nauvis:out/a/m0"),
                        Verdict("ok", "roboport", 57, 52, "nauvis:relay/r0")]

        class Link:
            def __init__(self, far):
                self.far = far

            def lua(self, text):
                return json.dumps(self.far)     # the indices the live read finds unreached

        ctx = flow.Ctx(self.dir, self.script, CAT, os.path.join(self.dir, "out"))
        ctx.surface = type("S", (), {"name": "nauvis", "mode": "play", "force": "player"})()
        # the pole and the assembler stand out of reach now; the new roboport is in reach, and
        # its own area (55 tiles) will cover the assembler once it is built: only the pole stays
        c = flow._unreached(ctx, Link([1, 3]), Rep)
        self.assertEqual(c.code, "UNREACHED")
        self.assertIn("1 of the 3 entities the paste lays", c.msg)
        self.assertIn("medium-electric-pole 63.5,34.5", c.msg)
        self.assertIn("1 of them are power-bridge poles", c.msg)
        self.assertIsNone(flow._unreached(ctx, Link([]), Rep))

    def test_the_diff_records_the_built_poles_for_the_cover_step(self):
        # 2.0.1: the cover step runs where there is no game link; the diff says which poles stand
        from fkcore.sense import Verdict
        ctx = flow.Ctx(self.dir, self.script, CAT, os.path.join(self.dir, "out"))
        ctx.surface = type("S", (), {"name": "nauvis"})()
        self.assertIsNone(flow._standing(ctx, "main"))           # no diff yet: as before

        class Rep:
            verdicts = [Verdict("ok", "medium-electric-pole", 3.5, 0.5, "nauvis:main/power/p0"),
                        Verdict("ghost", "medium-electric-pole", 9.5, 0.5, "nauvis:main/power/p1"),
                        Verdict("ok", "small-electric-pole", 1.5, 0.5, "nauvis:coal/power/p0"),
                        Verdict("ok", "assembling-machine-1", 1.5, 1.5, "nauvis:main/a/m0")]
        flow._save_standing(ctx, Rep)
        self.assertEqual(flow._standing(ctx, "main"), {"power/p0"})
        self.assertEqual(flow._standing(ctx, "coal"), {"power/p0"})
        Rep.verdicts = [Verdict("not-placed", "medium-electric-pole", 3.5, 0.5, "nauvis:main/power/p0")]
        flow._save_standing(ctx, Rep)                            # gone since: no longer standing
        self.assertEqual(flow._standing(ctx, "main"), set())
        self.assertEqual(flow._standing(ctx, "coal"), {"power/p0"})   # outside the scope: kept

    def test_the_kickoff_template_runs_through_the_routed_rates(self):
        # every new run's script (tier, then report_rates again) on the template as it ships: one
        # plot with the reactor, its pole line and the kit inside it, and a first factory of drills
        # into furnaces east of the kit; on paper (no terrain read).
        kick = os.path.join(os.path.dirname(__file__), "..", "kickoff", "template", "game")
        game = os.path.join(self.dir, "kick")
        shutil.copytree(kick, game)
        for name, old, new in (("nauvis.surface", "terrain  map", "terrain  none"),
                               ("nauvis.build.fkb", "read_terrain    map", "read_terrain    none")):
            with open(os.path.join(game, name), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn(old, text)
            with open(os.path.join(game, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text.replace(old, new))
        with open(os.path.join(game, "nauvis.surface"), encoding="utf-8") as fh:
            self.assertIn("design   nauvis.fk", fh.read())       # the plots are the world design
        with open(os.path.join(game, "world.fk"), "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\nore   = MinerRow<n=4, resource=iron-ore> @(1030, 1000)\n"
                     "smelt = SmelterRow<n=4, recipe=iron-plate> @(1030, 1016)\n"
                     "coal  = Chest<requester, item=coal, rate=1/s> @(1054, 1016)\n"
                     "box   = Chest<provider, limit=4> @(1054, 1030)\n"
                     "net ore: ore -> smelt\nnet fuel: coal -> smelt\nnet plates: smelt -> box\n")
        code, ctx = flow.run(os.path.join(game, "nauvis.build.fkb"), to="report_checks", cat=CAT,
                             echo=lambda _line: None)
        self.assertEqual(code, 0, ctx.log)
        with open(os.path.join(game, "out", "report_rates.txt"), encoding="utf-8") as fh:
            rates_txt = fh.read()
        self.assertEqual(rates_txt.count("# report_rates"), 2)
        # one plot, so the reactor and the kit are part of `world`, not factories of their own
        self.assertNotIn("rates plant (", rates_txt)
        self.assertRegex(rates_txt, r"routed world \(V2[^\n]*the machines settled in \d+ rounds")
        self.assertRegex(rates_txt, r"\n  smelt +1\.000 +1\.000 +1\.000  as nominal\n")
        with open(os.path.join(game, "out", "route.txt"), encoding="utf-8") as fh:
            self.assertIn("world: 3 routed, 0 kept (0 pinned from the committed .fkp), 0 failed",
                          fh.read())
        with open(os.path.join(game, "out", "floorplan.txt"), encoding="utf-8") as fh:
            self.assertIn("1 plots", fh.read())                 # the base's plot, and no other
        with open(os.path.join(game, "out", "tier.txt"), encoding="utf-8") as fh:
            self.assertIn("tier minimize (allowed: yellow)", fh.read())

    def test_a_moved_chest_routes_its_net_again(self):
        # 1.2 (the 0534 run): a chest moved one tile changes no belt end, only the tiles its
        # inserter reaches; its net's committed route was kept (pinned) and read UNROUTED
        small = os.path.join(self.dir, "small")
        os.makedirs(small)
        files = {
            "t.fk": "mine = MinerRow<n=1, resource=iron-ore> @(0, 0)\n"
                    "dst  = Chest<provider>                  @(20, 3)\n"
                    "net p: mine -> dst\n",
            "nauvis.surface": "surface nauvis\nmode play\nterrain none\n"
                              "place t = t plot 0,0 30x12\n",
            "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\n"
                                "place --keep pinned\nroute --only stale\nfloorplan\n"
                                "report_checks\nwrite_layout\n"}
        for name, text in files.items():
            with open(os.path.join(small, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        script = os.path.join(small, "nauvis.build.fkb")

        def build():
            code, ctx = flow.run(script, cat=CAT, echo=lambda _line: None)
            self.assertEqual(code, 0, ctx.log)
            with open(os.path.join(small, "out", "route.txt"), encoding="utf-8") as fh:
                route_txt = fh.read()
            with open(os.path.join(small, "out", "report_checks.txt"), encoding="utf-8") as fh:
                return route_txt, fh.read()

        build()
        route_txt, checks_txt = build()
        self.assertIn("kept      p: its carriers are already laid (pinned)", route_txt)
        with open(os.path.join(small, "t.fk"), encoding="utf-8") as fh:
            src = fh.read().replace("@(20, 3)", "@(20, 4)")
        with open(os.path.join(small, "t.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        route_txt, checks_txt = build()
        self.assertIn("stale     p: routed again: its ends moved since the committed .fkp "
                      "(dst.in1)", route_txt)
        self.assertIn("routed    p:", route_txt)
        self.assertNotIn("no-route", checks_txt)
        self.assertIn("1 nets: 1 connected", checks_txt)

    def test_a_row_added_is_patched_into_the_routes_that_stand(self):
        # 2.0 (Rory, 2026-10-21): "routing a new section into the old one, even as a bit of
        # spaghetti, beats ripping everything up". Before, iron and gear were laid again whole
        # (gear: 43 of its 69 belts stood where they were, 146 laid)
        def routes():
            lay = fkp.load(os.path.join(self.dir, "main.fkp"))
            out = {}
            for e in lay.entities.values():
                if e.owner.startswith("~"):
                    out.setdefault(e.owner[1:], set()).add((e.name, e.x, e.y, e.dir))
            return out

        self.build()
        first = routes()
        src = (self.read("main.fk")
               .replace("labs  = LabRow<n=10>", "gears2 = AsmRow<n=2, recipe=iron-gear-wheel> "
                                                "@(60, 34)\nlabs  = LabRow<n=10>")
               .replace("iron_smelt -> gears, circ", "iron_smelt -> gears, gears2, circ")
               .replace("net gear:   gears -> red", "net gear:   gears, gears2 -> red"))
        with open(os.path.join(self.dir, "main.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        route_txt = self.read("out/route.txt")
        self.assertIn("main: 0 routed, 10 kept, 2 patched (12 pinned from the committed .fkp)",
                      route_txt)
        # a new consumer: a splitter in place of one straight iron belt, a branch from it
        self.assertRegex(route_txt, r"patched   iron: 1 -> 5, gears2\.in1: a splitter in place of "
                                    r"~iron/b\d+, \d+ belts.*; 54 of 55 carriers kept\n")
        # a new driver: its belt side-loads onto the gear belt before its first split
        self.assertRegex(route_txt, r"patched   gear: 2 -> 3, gears2\.out: \d+ belts.*, "
                                    r"side-loaded onto ~gear/b\d+; 69 of 69 carriers kept\n")
        self.assertIn("12 nets: 12 connected, 0 open, 0 unrouted; 0 SPILL",
                      self.read("out/report_checks.txt"))
        now = routes()
        self.assertEqual({n: len(first[n] & now[n]) for n in first},
                         {n: len(first[n]) - (n == "iron") for n in first})

    def test_a_net_whose_sink_changed_is_routed_again(self):
        # the first lead run (green worker, 22:15): `net packs: X -> lab` became `X -> px` and
        # kept its name; the route stood as it was, the build said OK, the inserter fed the lab
        small = os.path.join(self.dir, "shop")
        os.makedirs(small)
        shop = ("rx  = Chest<requester, item=\"copper-plate,iron-gear-wheel\", rate=0.1/s> "
                "@(0, 1)\n"
                "X   = Assembler<recipe=automation-science-pack> @(2, 0)\n"
                "px  = Chest<provider, limit=4>                  @(6, 1)\n"
                "lab = Lab                                       @(8, 0)\n"
                "net xin:  rx -> X\n")
        files = {
            "shop.fk": shop + "net packs: X -> lab\n",
            "nauvis.surface": "surface nauvis\nmode play\nterrain none\n"
                              "place shop = shop plot 0,0 20x8\n",
            "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\n"
                                "place --keep pinned\nroute --only stale\nfloorplan\n"
                                "report_checks\nwrite_layout\n"}
        for name, text in files.items():
            with open(os.path.join(small, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

        def build():
            code, ctx = flow.run(os.path.join(small, "nauvis.build.fkb"), cat=CAT,
                                 echo=lambda _line: None)
            self.assertEqual(code, 0, ctx.log)
            with open(os.path.join(small, "out", "route.txt"), encoding="utf-8") as fh:
                route_txt = fh.read()
            with open(os.path.join(small, "out", "report_checks.txt"), encoding="utf-8") as fh:
                return route_txt, fh.read()

        build()
        route_txt, _checks = build()
        self.assertIn("kept      packs: its carriers are already laid (pinned)", route_txt)
        with open(os.path.join(small, "shop.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(shop + "net packs: X -> px\n")
        route_txt, checks_txt = build()
        self.assertIn("stale     packs: routed again: its committed route would SPILL: ~packs/i0 "
                      "drops into lab/m0, which is not a consumer of packs", route_txt)
        self.assertIn("routed    packs: 1 -> 1, 1 inserter (direct insertion)", route_txt)
        self.assertIn("kept      xin: its carriers are already laid (pinned)", route_txt)
        self.assertIn("2 nets: 2 connected, 0 open, 0 unrouted; 0 SPILL", checks_txt)
        lay = fkp.load(os.path.join(small, "shop.fkp"))
        g = connect.graph(lay, CAT)
        self.assertEqual([k for k, _via in g.pred.get("lab/m0", ())], [])  # nothing feeds the lab
        self.assertEqual([k for k, _via in g.pred.get("px/c0", ())], ["~packs/i0"])

    def build_bootstrap_factory(self, extra=""):
        """A small factory whose iron route tunnels under its fuel belt: every underground end
        has one maker, and that maker eats iron plates from the same net. ``extra`` adds source
        lines before the nets (a provider of the building item)."""
        boot = os.path.join(self.dir, "boot")
        os.makedirs(boot, exist_ok=True)
        files = {
            "t.fk": "fe   = Chest<requester, item=iron-plate>            @(0, 10)\n"
                    "ug   = Assembler<recipe=underground-belt>           @(30, 10)\n"
                    "gear = Assembler<recipe=iron-gear-wheel>            @(30, 20)\n"
                    "coal = Chest<requester, item=coal>                  @(15, 0)\n"
                    "box  = Chest<provider>                              @(15, 30)\n"
                    + extra
                    + "\nnet fuel: coal -> box\nnet iron: fe -> ug, gear\n",
            "nauvis.surface": "surface nauvis\nmode play\nterrain none\n"
                              "place boot = t plot 0,0 50x40\n",
            "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\nplace\n"
                                "route\nreport_checks\nwrite_layout\n",
        }
        for name, text in files.items():
            with open(os.path.join(boot, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        code, ctx = flow.run(os.path.join(boot, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _line: None)
        self.assertEqual(code, 0, ctx.log)
        return ctx

    def bootstrap_undergrounds(self):
        lay = fkp.load(os.path.join(self.dir, "boot", "t.fkp"))
        return [e for e in lay.entities.values()
                if e.name == "underground-belt" and e.attrs.get("net") == "iron"]

    def test_a_net_whose_route_needs_its_only_makers_item(self):
        # 2.0.4 A12 (the live run's mall): its last ghosts were underground belts carrying the
        # mall's own iron, and the only maker of underground belts sat behind them
        ctx = self.build_bootstrap_factory()
        boot = [c for _step, c in ctx.checks if c.code == "bootstrap"]
        self.assertEqual([c.where for c in boot], ["net boot/iron"])
        n = len(self.bootstrap_undergrounds())
        self.assertGreaterEqual(n, 2)                # the route really tunnels under the fuel
        self.assertIn(f"{n} underground-belt", boot[0].msg)
        self.assertIn("the only maker (boot/ug)", boot[0].msg)
        self.assertIn("takes iron-plate from this same net", boot[0].msg)
        self.assertIn("stock the underground-belt first", boot[0].msg)
        self.assertIn("bootstrap", self.read(os.path.join("boot", "out", "report_checks.txt")))
        # one line per net per run: report_checks again adds no matching line
        _lines, again = flow.s_report_checks(ctx, [])
        self.assertFalse([c for c in again if c.code == "bootstrap"])

    def test_a_building_item_from_outside_is_no_bootstrap(self):
        # the same design, with a requester chest of underground belts: a maker independent of
        # the net (the item comes from outside), so the net can be built from stock
        ctx = self.build_bootstrap_factory(
            "ugc  = Chest<requester, item=underground-belt>      @(0, 30)\n")
        self.assertEqual([c for _step, c in ctx.checks if c.code == "bootstrap"], [])
        self.assertGreaterEqual(len(self.bootstrap_undergrounds()), 2)   # the same design

    def test_a_malformed_script_is_refused(self):
        with open(self.script, "a", encoding="utf-8") as fh:
            fh.write("synth_design\n")
        with self.assertRaises(flow.FlowError) as cm:
            self.build()
        self.assertIn("unknown step 'synth_design'", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
