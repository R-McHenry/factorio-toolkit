"""3.1 (PLAN-3.1 31-placements, Rory 11-08): the registry of what was pasted (fkcore.placements),
the mismatch rule in sense and apply, fk paste / register / capture --from / look and diff by
placement id / adopt's set-line proposal. Offline: fake links, fixture scenes, temp games."""
import copy
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fkcore import __main__ as cli
from fkcore import adopt, alone, apply as applymod, capture, codec, flow, link, look, own, \
    placements, scene, sense, settings, wires
from fkcore import surface as surfacemod
from fkcore.catalog import Catalog
from tests.test_apply import FakeRcon, fake_snapshot
from tests.test_fkp import MINI
from tests.test_sense import AREA, NETS, SURFACE, WATCH, find, live_as_designed, surface

CAT = Catalog.load()
#: a captured block standing in the world: an assembler with a chest beside it
BLOCK = [{"src": None, "name": "assembling-machine-1", "x": 11.5, "y": 11.5, "direction": None,
          "attrs": {"recipe": "iron-gear-wheel"}},
         {"src": None, "name": "iron-chest", "x": 13.5, "y": 10.5, "direction": None, "attrs": {}}]


def rec(pid="std", module="std", area=(100, 100, 110, 110), **kw):
    fields = dict(id=pid, surface="nauvis", module=module, origin=[area[0], area[1]],
                  area=list(area), source="paste", count=2)
    fields.update(kw)
    return placements.Record(**fields)


class LinkCM:
    """A fake link as ``_game_link`` returns it: a context manager over ``lua``."""

    def __init__(self, lua=None):
        self.calls = []
        self._lua = lua

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def lua(self, body):
        self.calls.append(body)
        if self._lua is not None:
            got = self._lua(body)
            if got is not None:
                return got
        if "game.tick" in body:
            return "777"
        if "build_blueprint" in body:
            return "2"
        if "table_to_json" in body:
            return "{}"
        return "0"


def run_cli(argv, link_cm=None):
    out = io.StringIO()
    with mock.patch.object(cli, "_game_link", return_value=link_cm or LinkCM()), \
            redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


class RegistryTest(unittest.TestCase):
    """The json file: one record per artifact, replaced on a rebuild."""

    def setUp(self):
        self.game = tempfile.mkdtemp(prefix="fkplace-")
        self.addCleanup(shutil.rmtree, self.game, True)

    def test_round_trip_and_replace(self):
        self.assertEqual(placements.load(self.game, "nauvis"), {})
        a = rec()
        placements.put_all(self.game, "nauvis", [a])
        self.assertTrue(os.path.exists(os.path.join(self.game, "out", "placements", "nauvis.json")))
        got = placements.load(self.game, "nauvis")
        self.assertEqual(got, {"std": a})
        # the same id again: replaced, not piled up
        placements.put_all(self.game, "nauvis", [rec(count=5)])
        got = placements.load(self.game, "nauvis")
        self.assertEqual([r.count for r in got.values()], [5])
        self.assertEqual(placements.find(self.game, "std")[0], "nauvis")
        self.assertIsNone(placements.find(self.game, "nope"))

    def test_unique_id_is_a_rebuild_inside_the_old_area_else_a_new_name(self):
        recs = {"std": rec()}
        self.assertEqual(placements.unique_id(recs, "std", "std", (104, 104)), "std")   # inside
        self.assertEqual(placements.unique_id(recs, "std", "std", (200, 0)), "std-2")   # elsewhere
        self.assertEqual(placements.unique_id(recs, "std", "other", (104, 104)), "std-2")
        self.assertEqual(placements.unique_id({}, "a b.json", "x", (0, 0)), "a-b.json")

    def test_rows_key_is_relative_to_the_origin(self):
        here = placements.rows_key(BLOCK, (10, 10))
        moved = [dict(r, x=r["x"] + 50) for r in BLOCK]
        self.assertEqual(placements.rows_key(moved, (60, 10)), here)
        self.assertNotEqual(placements.rows_key(moved, (10, 10)), here)
        self.assertTrue(here.startswith("rows:"))

    def test_resolve_an_area_or_an_id(self):
        placements.put_all(self.game, "nauvis", [rec()])
        self.assertEqual(placements.resolve(self.game, "1,2,3,4"), (None, (1, 2, 3, 4)))
        r, area = placements.resolve(self.game, "std")
        self.assertEqual((r.id, area), ("std", (100, 100, 110, 110)))
        with self.assertRaisesRegex(KeyError, "no placement 'x' \\(placements: std\\)"):
            placements.resolve(self.game, "x")
        self.assertIn("placement std: std at 100,100, area 100,100,110,110, 2 entities (paste)",
                      placements.head(r))


class ApplyRecordsTest(unittest.TestCase):
    """A build's apply records one placement per plot, and the shared infrastructure."""

    def setUp(self):
        self.game = tempfile.mkdtemp(prefix="fkplace-")
        self.addCleanup(shutil.rmtree, self.game, True)
        self.s = surface()

    def test_from_apply_one_per_plot_plus_shared(self):
        rows = applymod.scope_rows(self.s)
        recs = placements.from_apply(self.s, rows, CAT, {"mini": "gearbox"}, None, 42, "fk build")
        by = {r.id: r for r in recs}
        self.assertEqual(sorted(by), ["mini", "shared"])
        m = by["mini"]
        self.assertEqual((m.module, m.instance, m.origin, m.rot, m.count, m.tick, m.source),
                         ("gearbox", "mini", [10, 0], 0, 19, 42, "build"))
        self.assertEqual(m.area[:2], [10, 0])                    # the plot's box, grown to its rows
        self.assertGreaterEqual(m.area[2], 17)
        self.assertTrue(m.artifact.startswith("rows:"))          # no compile store entry
        self.assertEqual((by["shared"].module, by["shared"].count), ("nauvis", 1))
        # the design's own placements explain nothing in its own diff; another one does
        others = placements.explaining({r.id: r for r in recs + [rec()]}, self.s)
        self.assertEqual([r.id for r in others], ["std"])

    def test_the_apply_reports_its_rows_and_tick_and_a_rebuild_replaces(self):
        rows = applymod.scope_rows(self.s, keys=["nauvis:mini/"])
        want = [(r["name"], float(r["x"]), float(r["y"])) for r in rows]
        for _ in range(2):
            r = FakeRcon(want)
            with mock.patch.object(link, "snapshot", fake_snapshot(want)):
                rep = applymod.apply(r, self.s, CAT, keys=["nauvis:mini/"], free=True, force="lab")
            self.assertEqual((len(rep.rows), rep.tick), (19, 1))
            placements.put_all(self.game, "nauvis", placements.from_apply(
                self.s, rep.rows, CAT, {}, None, rep.tick, "fk build"))
        got = placements.load(self.game, "nauvis")
        self.assertEqual(sorted(got), ["mini"])                   # one record, not two


class AloneRecordTest(unittest.TestCase):
    """A build alone records its slot in the game's registry for that surface."""

    def test_record_placement(self):
        run = tempfile.mkdtemp(prefix="fkalone-")
        self.addCleanup(shutil.rmtree, run, True)
        game = os.path.join(run, "game")
        os.makedirs(game)
        example = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples",
                               "smelting.fk")
        shutil.copy(example, os.path.join(game, "smelting.fk"))
        with open(os.path.join(game, "nauvis.surface"), "w", newline="\n") as fh:
            fh.write("surface  nauvis\nterrain  none\ncatalog  base\n\n"
                     "place iron = smelting plot 10,90 26x26\n")
        ws, plot = alone.prepare(game, "iron")
        sf = alone.surface_of(game, "iron")
        slot = alone.slots(game)["iron"]
        line = alone.record_placement(game, "iron", "lab", sf, plot, slot)
        self.assertIn("placement iron: recorded in out/placements/lab.json", line)
        got = placements.load(game, "lab")["iron"]
        self.assertEqual((got.module, got.source, got.origin, got.surface),
                         ("smelting", "alone", [plot[0], plot[1]], "lab"))
        self.assertEqual(tuple(got.area), alone.box(*slot))
        # the build records it once its apply step ran (flow.run echoed one), not before
        steps = ["[ 1/3] read_surface lab", "[12/13] apply lab area 0,0,1,1: 3 entities"]

        def fake_run(script, cat=None, echo=None, link=None, extra=None, compiled=None):
            for s in steps:
                echo(s)
            return 0, mock.Mock()
        r = mock.Mock()
        r.lua.return_value = "0"
        with mock.patch.object(alone.flow, "run", side_effect=fake_run):
            built = alone.build(r, game, "iron")
        self.assertTrue(any("placement iron: recorded" in ln for ln in built.lines))


class PasteTest(unittest.TestCase):
    """fk paste FILE --at X,Y [--rot R] [--as NAME]: ghosts where the file's origin goes."""

    def setUp(self):
        self.game = tempfile.mkdtemp(prefix="fkpaste-")
        self.addCleanup(shutil.rmtree, self.game, True)
        with open(os.path.join(self.game, "nauvis.surface"), "w", newline="\n") as fh:
            fh.write("surface  nauvis\nterrain  none\ncatalog  base\n")
        os.makedirs(os.path.join(self.game, "captured"))
        self.file = os.path.join(self.game, "captured", "std.json")
        with open(self.file, "w") as fh:
            json.dump({"bp": codec.blueprint(BLOCK)}, fh)

    def test_paste_rows_put_the_origin_at_and_turn_about_it(self):
        rows = placements.paste_rows(self.file, "std", CAT, (100, 50))
        self.assertEqual([(r["name"], r["x"], r["y"]) for r in rows],
                         [("assembling-machine-1", 111.5, 61.5), ("iron-chest", 113.5, 60.5)])
        self.assertEqual(rows[0]["attrs"]["recipe"], "iron-gear-wheel")
        self.assertEqual(rows[0]["src"], "std/assembling-machine-10")
        turned = placements.paste_rows(self.file, "std", CAT, (0, 0), 1)
        # (11.5, 11.5) a quarter turn clockwise about the origin is (-11.5, 11.5)
        self.assertEqual([(r["x"], r["y"]) for r in turned], [(-11.5, 11.5), (-10.5, 13.5)])

    def test_the_command_pastes_and_records_and_a_rebuild_replaces(self):
        lk = LinkCM()
        code, out = run_cli(["paste", self.game, "captured/std.json", "--at", "100,50"], lk)
        self.assertEqual(code, 0, out)
        self.assertIn("paste captured/std.json: 2 entities as ghosts on nauvis (force player), "
                      "origin 100,50, 2 placed by the game; robots build them", out)
        self.assertIn("placement std: std at 100,50, area 100,50,114,63, 2 entities, rows:", out)
        paste = next(c for c in lk.calls if "build_blueprint" in c)
        self.assertIn("superforced", paste)
        self.assertFalse(any("register" in c or "on_event" in c for c in lk.calls))
        got = placements.load(self.game, "nauvis")["std"]
        self.assertEqual((got.source, got.file, got.tick, got.count, got.origin),
                         ("paste", "captured/std.json", 777, 2, [100, 50]))
        # pasted again at the same spot: the same record; elsewhere: another
        run_cli(["paste", self.game, "captured/std.json", "--at", "100,50"])
        self.assertEqual(sorted(placements.load(self.game, "nauvis")), ["std"])
        run_cli(["paste", self.game, "captured/std.json", "--at", "300,50", "--as", "far"])
        self.assertEqual(sorted(placements.load(self.game, "nauvis")), ["far", "std"])
        run_cli(["paste", self.game, "captured/std.json", "--at", "500,50"])
        self.assertEqual(sorted(placements.load(self.game, "nauvis")), ["far", "std", "std-2"])
        code, out = run_cli(["placements", self.game])
        self.assertIn("placements on nauvis: 3", out)

    def test_a_free_surface_revives(self):
        lk = LinkCM(lambda body: "2 0" if "revive" in body else None)
        code, out = run_cli(["paste", self.game, "captured/std.json", "--at", "0,0",
                             "--surface", "lab"], lk)
        self.assertEqual(code, 0, out)
        self.assertIn("(force lab)", out)
        self.assertIn("2 revived (free surface)", out)
        self.assertEqual(sorted(placements.load(self.game, "lab")), ["std"])


class MismatchTest(unittest.TestCase):
    """Rory 11-08: a conflicting design is a MISMATCH that names its owner; mating is ok."""

    def setUp(self):
        self.s = surface()

    def run_sense(self, live, recs=(), rec_own=None):
        return sense.sense(self.s, live, CAT, AREA, WATCH, net_items=NETS, own=rec_own,
                           placements=list(recs))

    def test_a_placement_on_a_design_tile_is_the_owner(self):
        live = copy.deepcopy(live_as_designed(self.s))
        live["things"].remove(find(live, "transport-belt", 10.5, 0.5))
        live["things"].append(scene.thing(name="iron-chest", type="container", x=10.5, y=0.5))
        std = rec(area=(10, 0, 12, 2))
        rep = self.run_sense(live, [std])
        (c,) = sense.conflicts(rep)
        self.assertEqual((c.key, c.stands, c.owner),
                         ("nauvis:mini/~iron/b0", "iron-chest", "placement std"))
        self.assertIn("fk capture --from std --into captured/std.json", c.resolve)
        self.assertEqual(rep.marks, [])
        self.assertEqual(rep.counts().get("conflict"), 1)

    def test_inside_another_placement_is_placed_not_a_foreign_change(self):
        live = copy.deepcopy(live_as_designed(self.s))
        live["things"].append(scene.thing(name="iron-chest", type="container", x=45.5, y=2.5))
        rep = self.run_sense(live, [rec(area=(44, 0, 48, 6))])
        v = next(v for v in rep.verdicts if v.name == "iron-chest")
        self.assertEqual((v.verdict, v.key), ("placed", "nauvis:placement/std"))
        self.assertIn("inside placement std (std), not this design's: fk look std", v.detail)
        self.assertEqual((rep.marks, rep.changes), ([], []))
        # without the record it is a foreign change in sanctioned space, marked as before
        self.assertEqual(self.run_sense(live).counts().get("marked"), 1)

    def test_mating_is_ok_and_the_toolkits_own_still_upgrades(self):
        live = copy.deepcopy(live_as_designed(self.s))
        rep = self.run_sense(live, [rec(area=(8, -2, 20, 10))])       # a placement over the plot
        self.assertEqual(rep.counts(), {"ok": 20})
        self.assertEqual(sense.conflicts(rep), [])
        # the toolkit's own on a design tile (the own record has it) goes up or fresh, no mismatch
        live["things"].remove(find(live, "transport-belt", 10.5, 0.5))
        live["things"].append(scene.thing(name="iron-chest", type="container", x=10.5, y=0.5))
        mine = {own.at("iron-chest", 10.5, 0.5): own.Row("nauvis:mini/old/c0", "iron-chest",
                                                           10.5, 0.5, None, None)}
        rep = self.run_sense(live, [], mine)
        self.assertEqual(sense.conflicts(rep), [])
        self.assertEqual(rep.counts().get("other-entity"), 1)

    def test_the_apply_refuses_the_tile_and_pastes_the_rest(self):
        live = copy.deepcopy(live_as_designed(self.s))
        live["things"].remove(find(live, "transport-belt", 10.5, 0.5))
        live["things"].append(scene.thing(name="iron-chest", type="container", x=10.5, y=0.5))
        std = rec(area=(10, 0, 12, 2))
        rows = applymod.scope_rows(self.s, keys=["nauvis:mini/"])
        things = [(r["name"], float(r["x"]), float(r["y"])) for r in rows]
        r = FakeRcon(things)
        with mock.patch.object(link, "snapshot", fake_snapshot(things)), \
                mock.patch.object(applymod.scene, "from_capture", return_value=live), \
                mock.patch.object(wires, "run", return_value=wires.Pass()):
            rep = applymod.apply(r, self.s, CAT, keys=["nauvis:mini/"], policy=WATCH,
                                 placements=[std], own=own.rows_of(self.s))
        self.assertEqual([c.owner for c in rep.refused], ["placement std"])
        self.assertEqual(rep.design, 18)
        self.assertNotIn("nauvis:mini/~iron/b0", [row["src"] for row in rep.rows])
        text = "\n".join(rep.lines())
        self.assertIn("mismatch: 1 design tiles", text)
        self.assertIn("placement std; refused, not pasted. fk capture --from std", text)
        bp = next(c for c in r.calls if "build_blueprint" in c)
        self.assertNotIn("~iron/b0", bp)          # tags.src of the refused row is not in the paste


class GameBase(unittest.TestCase):
    """A game codebase with the mini factory laid out (the test_sense fixture on disk)."""

    def setUp(self):
        self.game = tempfile.mkdtemp(prefix="fkgame-")
        self.addCleanup(shutil.rmtree, self.game, True)
        self.write("nauvis.surface", "surface  nauvis\nterrain  none\ncatalog  base\n"
                   "watch plots: keep\nwatch sanctioned: mark 2h\n\n"
                   "place mini = mini plot 10,0 7x7\n")
        self.write("nauvis.fkp", SURFACE.replace("size 7x7", "size 7x7 module=mini"))
        self.write("mini.fkp", MINI)
        self.write("mini.fk", "gears = AsmRow<n=2, recipe=iron-gear-wheel> @(0, 2)\n")
        self.s = look.composed(self.game, CAT)[3]

    def write(self, name, text):
        with open(os.path.join(self.game, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.game, name), encoding="utf-8") as fh:
            return fh.read()

    def snap(self, live):
        """``link.snapshot`` answering with ``live`` (a scene) as a capture dump."""
        def fake(r, surface_name, area, tag="snap", keep=True):
            return {"tick": live.get("tick"), "area": list(area), "things": [
                {"n": t["name"], "t": t["type"], "x": t["x"], "y": t["y"], "d": t["direction"],
                 "g": t["ghost"], "dc": t["decon"], "force": t["force"], "rc": t["recipe"],
                 "lu": t["last_user"], "ug": t["ug"], "it": t["items"],
                 "box": [min(a for a, _b in t["tiles"]) + 0.1, min(b for _a, b in t["tiles"]) + 0.1,
                         max(a for a, _b in t["tiles"]) + 0.9, max(b for _a, b in t["tiles"]) + 0.9]}
                for t in live["things"]]}
        return fake


class RegisterTest(GameBase):
    """fk register AREA MODULE: what stands is that artifact; the differences are reported."""

    def test_register_a_factory_records_and_owns_what_stands(self):
        live = copy.deepcopy(live_as_designed(self.s))
        live["things"].append(scene.thing(name="wooden-chest", type="container", x=12.5, y=4.5))
        with mock.patch.object(link, "snapshot", self.snap(live)):
            code, out = run_cli(["register", self.game, "8,-2,20,10", "mini"])
        self.assertEqual(code, 0, out)
        self.assertIn("register 8,-2,20,10 as mini: 20 entities stand there, recorded as mini (a "
                      "factory of this surface)", out)
        self.assertIn("own: 20 standing entities are the toolkit's own under mini now (1 of them "
                      "not where the design has them", out)
        got = placements.load(self.game, "nauvis")["mini"]
        self.assertEqual((got.module, got.instance, got.origin, got.source, got.count),
                         ("mini", "mini", [10, 0], "register", 20))
        mine = own.load(self.game, "nauvis")
        self.assertEqual(mine[own.at("wooden-chest", 12.5, 4.5)].key,
                         "nauvis:mini/registered/wooden-chest0")
        self.assertEqual(mine[own.at("transport-belt", 10.5, 0.5)].key, "nauvis:mini/~iron/b0")
        # the differences, as a diff says them: the chest is the toolkit's own now, dropped
        self.assertIn("differences against the design", out)
        self.assertIn("unowned  wooden-chest 12.5,4.5 nauvis:mini/registered/wooden-chest0: the "
                      "toolkit's own, dropped from the design", out)

    def test_register_as_a_name_is_a_placement_only(self):
        live = copy.deepcopy(live_as_designed(self.s))
        live["things"].append(scene.thing(name="wooden-chest", type="container", x=45.5, y=2.5))
        with mock.patch.object(link, "snapshot", self.snap(live)):
            code, out = run_cli(["register", self.game, "44,0,48,6", "--as", "box"])
        self.assertEqual(code, 0, out)
        self.assertIn("recorded as box (no factory of this surface places it: a placement only)", out)
        self.assertIsNone(own.load(self.game, "nauvis"))
        got = placements.load(self.game, "nauvis")["box"]
        self.assertEqual((got.module, got.instance, got.area), ("box", None, [44, 0, 48, 6]))
        code, out = run_cli(["register", self.game, "44,0,48,6"])
        self.assertEqual(code, 2)


class LookDiffByIdTest(GameBase):
    """fk look ID / fk diff ID: the existing look and diff over the placement's area."""

    def setUp(self):
        super().setUp()
        placements.put_all(self.game, "nauvis", [rec("std", area=(44, 0, 48, 6))])

    def test_diff_by_id_is_headed_by_the_placement(self):
        live = copy.deepcopy(live_as_designed(self.s))
        live["things"].append(scene.thing(name="wooden-chest", type="container", x=45.5, y=2.5))
        with mock.patch.object(link, "snapshot", self.snap(live)):
            code, out = run_cli(["diff", self.game, "std"])
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("placement std: std at 44,0, area 44,0,48,6, 2 entities (paste)\n"
                                       "sense area 44,0,48,6 tick 4200000: placed 1\n"), out)
        self.assertIn("placed   wooden-chest 45.5,2.5 nauvis:placement/std: inside placement std", out)
        with self.assertRaisesRegex(SystemExit, "no placement 'nope' \\(placements: std\\)"):
            run_cli(["diff", self.game, "nope"])

    def test_look_by_id_resolves_the_area(self):
        seen = {}

        def fake_run(r, game, cat, area=None, *a, **kw):
            seen["area"] = area
            lk = mock.Mock()
            lk.lines.return_value = ["look lines"]
            return lk
        with mock.patch.object(look, "run", side_effect=fake_run):
            code, out = run_cli(["look", self.game, "--source", "world", "--area", "std"])
        self.assertEqual((code, seen["area"]), (0, (44, 0, 48, 6)))
        self.assertTrue(out.startswith("placement std: std at 44,0"), out)


class CaptureFromTest(GameBase):
    """fk capture --from: the selection as source, anchored where it stands."""

    def test_anchored_file_and_the_two_lines(self):
        got = {"bp": codec.blueprint(BLOCK), "n": 2, "names": {"assembling-machine-1": 1,
                                                                  "iron-chest": 1},
               "at": [[11.5, 11.5, "assembling-machine-1"], [13.5, 10.5, "iron-chest"]]}
        with mock.patch.object(capture, "from_game", return_value=got) as fg:
            code, out = run_cli(["capture", self.game, "--from", "10,10,16,14", "--into",
                                 "captured/std.json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(fg.call_args.args[1:], ("nauvis", "player", (10, 10, 16, 14)))
        data = json.loads(self.read(os.path.join("captured", "std.json")))
        self.assertEqual(data["anchor"], [10, 10])
        self.assertEqual([(e["name"], e["wx"], e["wy"], e["bx"], e["by"]) for e in data["entities"]],
                         [("assembling-machine-1", 1.5, 1.5, 11.5, 11.5),
                          ("iron-chest", 3.5, 0.5, 13.5, 10.5)])
        self.assertEqual(data["names"], {"asm1": 0})
        self.assertIn('    std = Literal<file="captured/std.json"> @(10, 10)', out)
        self.assertIn("    net out: std.asm1 -> <your new instance>", out)
        self.assertIn("on a plot at X,Y: @(10 - X, 10 - Y)", out)
        # by placement id: the anchor is the placement's origin
        placements.put_all(self.game, "nauvis", [rec("std", area=(10, 10, 16, 14), origin=[10, 10])])
        with mock.patch.object(capture, "from_game", return_value=got):
            code, out = run_cli(["capture", self.game, "--from", "std"])
        self.assertEqual(code, 0, out)
        self.assertIn("into captured/std.json, anchored at 10,10 on nauvis", out)


class MateRoundTripTest(unittest.TestCase):
    """The mating workflow: capture a standing block, write a module with the Literal plus a new
    net ending on one of its machines, build; the standing entities are ok, the new carriers
    ghosts, no mismatch."""

    def setUp(self):
        self.game = tempfile.mkdtemp(prefix="fkmate-")
        self.addCleanup(shutil.rmtree, self.game, True)
        self.write("nauvis.surface", "surface  nauvis\nterrain  none\ncatalog  base\n\n"
                   "place mate = mate plot 0,0 40x40\n")
        self.write("nauvis.build.fkb", "read_surface    nauvis\nread_terrain    none\nelaborate\n"
                   "size\nplace           --keep pinned\nroute           --only stale\n"
                   "floorplan\nwrite_layout\napply           --scope all\ndiff --scope all\n")
        # the standing block, built in the world (by hand, say)
        self.standing = [scene.thing(name=r["name"], type=CAT.kind(r["name"]), x=r["x"], y=r["y"],
                                     tiles=[list(t) for t in CAT.tiles(r["name"], r["x"], r["y"], 0)],
                                     recipe=r["attrs"].get("recipe"), force="player")
                         for r in BLOCK]
        self.pasted = []

    def write(self, name, text):
        with open(os.path.join(self.game, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def snapshot(self, r, surface_name, area, tag="snap", keep=True):
        """What stands: the block, plus a ghost of every row pasted so far."""
        things = [{"n": t["name"], "t": t["type"], "x": t["x"], "y": t["y"], "d": 0, "g": False,
                   "force": "player", "rc": t["recipe"],
                   "box": [min(a for a, _b in t["tiles"]) + 0.1, min(b for _a, b in t["tiles"]) + 0.1,
                           max(a for a, _b in t["tiles"]) + 0.9, max(b for _a, b in t["tiles"]) + 0.9]}
                  for t in self.standing]
        built = {(t["n"], t["x"], t["y"]) for t in things}
        for row in self.pasted:
            if (row["name"], float(row["x"]), float(row["y"])) in built:
                continue
            tiles = CAT.tiles(row["name"], float(row["x"]), float(row["y"]), row["direction"] or 0)
            things.append({"n": row["name"], "t": CAT.kind(row["name"]), "x": float(row["x"]),
                           "y": float(row["y"]), "d": row["direction"] or 0, "g": True,
                           "force": "player",
                           "box": [min(a for a, _b in tiles) + 0.1, min(b for _a, b in tiles) + 0.1,
                                   max(a for a, _b in tiles) + 0.9, max(b for _a, b in tiles) + 0.9]})
        return {"tick": 99, "area": list(area), "things": things}

    def paste(self, r, surface, force, bp, at):
        rows, _desc, _wires = codec.parse_blueprint(bp)
        self.pasted += rows
        return str(len(rows))

    def test_capture_write_place_build(self):
        got = {"bp": codec.blueprint(BLOCK), "n": 2,
               "names": {"assembling-machine-1": 1, "iron-chest": 1},
               "at": [[11.5, 11.5, "assembling-machine-1"], [13.5, 10.5, "iron-chest"]]}
        with mock.patch.object(capture, "from_game", return_value=got):
            code, out = run_cli(["capture", self.game, "--from", "10,10,16,14", "--into",
                                 "captured/std.json"])
        self.assertEqual(code, 0, out)
        # a new module written against it: the Literal at its anchor, a new chest fed from asm1
        self.write("mate.fk", 'std = Literal<file="captured/std.json"> @(10, 10)\n'
                              "box = Chest<provider> @(22, 11)\n"
                              "net out: std.asm1 -> box\n")
        lk = LinkCM()
        said = []
        with mock.patch.object(link, "snapshot", self.snapshot), \
                mock.patch.object(link, "paste", self.paste), \
                mock.patch.object(link, "ghosts", return_value={"n": 0, "missed": {}}), \
                mock.patch.object(wires, "run", return_value=wires.Pass()), \
                mock.patch.object(flow, "_read_roboports", return_value=[]), \
                mock.patch("fkcore.supply.read", return_value=None), \
                mock.patch("fkcore.supply.mark_ghosts"):
            code, ctx = flow.run(os.path.join(self.game, "nauvis.build.fkb"), cat=CAT,
                                 echo=said.append, link=lk)
        self.assertEqual(code, 0, "\n".join(said))
        rep = ctx.last_diff
        by = {v.key: v for v in rep.verdicts}
        asm = by["nauvis:mate/std/assembling-machine-10"]
        chest = by["nauvis:mate/std/iron-chest0"]
        self.assertEqual((asm.verdict, chest.verdict), ("ok", "ok"))        # mated
        new = [v for k, v in by.items() if "/~out/" in k or k.endswith("/box/c0")
               or "/box/" in k]
        self.assertTrue(new, sorted(by))
        self.assertEqual({v.verdict for v in new}, {"ghost"})                # the new ones, ghosts
        self.assertEqual(sense.conflicts(rep), [])
        self.assertNotIn("mismatch", "\n".join(said))
        got = placements.load(self.game, "nauvis")
        self.assertEqual(sorted(got), ["mate"])
        self.assertEqual((got["mate"].module, got["mate"].origin, got["mate"].tick),
                         ("mate", [0, 0], 99))
        # the pasted rows hold the Literal's entities too (the paste lands them on the standing
        # ones, which the game leaves as they are) and the new carriers
        names = {r["name"] for r in self.pasted}
        self.assertIn("assembling-machine-1", names)
        self.assertTrue(names & {"transport-belt", "inserter", "fast-inserter", "burner-inserter",
                                 "long-handed-inserter"}, names)


class AdoptProposalTest(GameBase):
    """fk adopt PLACEMENT|AREA: a changed setting becomes a proposed set line."""

    def drift(self, key, name, fields):
        return settings.Drift(key, name, 11.5, 3.5, "Rory_618", "x", "y", fields=fields)

    def test_propose_set_lines_and_notes(self):
        modules = {"mini": "mini"}
        props = adopt.propose([
            self.drift("nauvis:mini/gears/m0", "assembling-machine-1", {"bar": 4}),
            self.drift("nauvis:mini/gears/o0", "fast-inserter",
                       {"control_behavior": {"circuit_condition": {"constant": 5}}}),
            self.drift("nauvis:mini/gears/m1", "assembling-machine-1", {"recipe": "pipe"}),
            self.drift("nauvis:mini/gears/i0", "fast-inserter", {"vectors": "pick=1 drop=2"}),
            settings.Drift("nauvis:mini/gears/i1", "fast-inserter", 1, 1, None, "", "", wires=True)],
            CAT, modules)
        self.assertEqual([p.line for p in props], [
            "set gears: bp.bar=4",
            'set gears.out: cb.circuit_condition={"constant":5}',
            None, None])
        self.assertIn("recipe pipe: a parameter of the instance, not a set line", props[2].note)
        self.assertIn("needs a Literal patch", props[3].note)
        self.assertEqual(props[0].diff_lines(self.read("mini.fk")), [
            "@@ mini.fk (mini/gears/m0)",
            " gears = AsmRow<n=2, recipe=iron-gear-wheel> @(0, 2)",
            "+set gears: bp.bar=4"])
        done = adopt.write_proposals(self.game, props)
        self.assertEqual(done, [("mini", "set gears: bp.bar=4"),
                                ("mini", 'set gears.out: cb.circuit_condition={"constant":5}')])
        self.assertEqual(self.read("mini.fk").splitlines()[:2], [
            "gears = AsmRow<n=2, recipe=iron-gear-wheel> @(0, 2)",
            'set gears.out: cb.circuit_condition={"constant":5}    # fk adopt'])

    def test_the_command_prints_the_diff_and_writes_on_request(self):
        placements.put_all(self.game, "nauvis", [rec("mini", module="mini", area=(8, -2, 20, 10),
                                                      origin=[10, 0], source="build")])
        rep = sense.SenseReport([8, -2, 20, 10], 1, [], [], [], [], [], {})
        rep.settings = [self.drift("nauvis:mini/gears/m0", "assembling-machine-1", {"bar": 4})]
        with mock.patch.object(applymod, "diff", return_value=rep):
            code, out = run_cli(["adopt", self.game, "mini"])
        self.assertEqual(code, 0, out)
        self.assertIn("placement mini: mini at 10,0", out)
        self.assertIn("adopt mini: 1 setting changes on standing design entities", out)
        self.assertIn("+set gears: bp.bar=4", out)
        self.assertIn("--write appends these set lines", out)
        self.assertNotIn("set gears", self.read("mini.fk"))
        with mock.patch.object(applymod, "diff", return_value=rep):
            code, out = run_cli(["adopt", self.game, "8,-2,20,10", "--write"])
        self.assertIn("wrote mini.fk: set gears: bp.bar=4", out)
        self.assertIn("set gears: bp.bar=4    # fk adopt", self.read("mini.fk"))

    def test_a_foreign_carrier_is_v1_adoption_and_a_machine_needs_a_literal_patch(self):
        live = copy.deepcopy(live_as_designed(self.s))
        # a belt next to the iron belt row (a fix), and a chest in the plot
        live["things"] += [scene.thing(name="transport-belt", type="transport-belt", x=10.5,
                                       y=1.5, direction=4, last_user="Rory_618"),
                           scene.thing(name="wooden-chest", type="container", x=15.5, y=4.5)]
        rep = sense.sense(self.s, live, CAT, [8, -2, 20, 10], WATCH)
        with mock.patch.object(applymod, "diff", return_value=rep):
            code, out = run_cli(["adopt", self.game, "8,-2,20,10"])
        self.assertEqual(code, 0, out)
        self.assertIn("2 things stand here that the design does not have", out)
        self.assertIn("transport-belt at 10.5,1.5 (hand edit by Rory_618): a carrier next to net "
                      "mini/iron: fk adopt 10.5,1.5 --into mini/iron", out)
        self.assertIn("wooden-chest at 15.5,4.5 (unknown): needs a Literal patch: fk capture "
                      "--from 8,-2,20,10 --into captured/patch.json", out)


if __name__ == "__main__":
    unittest.main()
