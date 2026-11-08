"""fkcore.look against fixture captures and a fake link (no game): report, renders, notify, marks."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import fkp, link, look, scene
from fkcore import surface as surfacemod
from fkcore.catalog import Catalog

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "lab-sense")
AREA = (305, 415, 353, 449)
TICK = 200000
SANCTIONED = (307.5, 430.5)          # west of the iron plot, inside the look


def _touches(tiles, area):
    return any(area[0] <= t[0] < area[2] and area[1] <= t[1] < area[3] for t in tiles)


def capture(s, area=AREA, tick=TICK, extra=()):
    """A capture dump (``link.snapshot`` rows) of the design as a finished apply leaves it."""
    rows = []
    for e in sorted(s.entities.values(), key=lambda e: e.key):
        if not _touches(e.tiles, area):
            continue
        xs, ys = [t[0] for t in e.tiles], [t[1] for t in e.tiles]
        rows.append({"n": e.name, "t": CAT.kind(e.name), "x": e.x, "y": e.y, "d": e.dir or 0,
                     "g": False, "force": "lab", "rc": e.attrs.get("recipe"),
                     "box": [min(xs) + 0.1, min(ys) + 0.1, max(xs) + 0.9, max(ys) + 0.9]})
    return {"tick": tick, "area": list(area), "things": rows + list(extra)}


def belt(x, y, d=4, lu=None):
    row = {"n": "transport-belt", "t": "transport-belt", "x": x, "y": y, "d": d, "g": False,
           "force": "lab", "box": [x - 0.4, y - 0.4, x + 0.4, y + 0.4]}
    if lu:
        row["lu"] = lu
    return row


def ug(x, y, kind="input", d=4, ghost=False, name="underground-belt", pair=None):
    row = {"n": name, "t": "underground-belt", "x": x, "y": y, "d": d, "g": ghost,
           "force": "lab", "ug": kind, "box": [x - 0.4, y - 0.4, x + 0.4, y + 0.4]}
    if pair is not None:
        row["pair"] = list(pair)
    return row


def fix_tile(s):
    """A free tile inside a plot next to a route belt (a fix to that net): (x, y)."""
    for key in sorted(s.entities):
        e = s.entities[key]
        if "/~" not in key or e.name != "transport-belt":
            continue
        for tx, ty in e.tiles:
            for nx, ny in ((tx, ty - 1), (tx, ty + 1), (tx - 1, ty), (tx + 1, ty)):
                if (nx, ny) not in s.tiles and s.whose(nx, ny)[0] == "plot":
                    return nx, ny
    raise AssertionError("no free tile next to a route")


class FakeRcon:
    def __init__(self):
        self.calls = []

    def lua(self, body):
        self.calls.append(body)
        return "ok"

    def said(self):
        return [c for c in self.calls if "game.print" in c]


class LookTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fklook-")
        for name in os.listdir(GAME):
            if os.path.isfile(os.path.join(GAME, name)):
                shutil.copy(os.path.join(GAME, name), self.dir)
        self.sf, _lay, _path, self.s = look.composed(self.dir, CAT)
        fx, fy = fix_tile(self.s)
        self.foreign = [belt(*SANCTIONED, lu="Rory_618"), belt(fx + 0.5, fy + 0.5, d=8)]

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def report(self, extra=(), notify=None, watch=None):
        live = scene.from_capture(capture(self.s, extra=extra))
        return look.report(self.s, live, CAT, AREA, look.policy(self.sf, notify, watch))

    def run_look(self, extra=(), **kw):
        r = FakeRcon()
        snap = lambda _r, _surface, area, tag="snap", keep=True: capture(self.s, area,
                                                                          extra=extra)
        with mock.patch.object(link, "snapshot", snap):
            lk = look.run(r, self.dir, CAT, AREA, **kw)
        return r, lk

    def inbox(self):
        path = os.path.join(self.dir, "out", "inbox.txt")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()

    def test_a_look_says_when_the_source_moved_on_from_the_fkp(self):
        # 2.0.4 (the second lead run, 2026-10-22): a paste from stale checkpoints wrote red.fkp
        # with the old recipe, and the look, which judges against the .fkp, said OK
        import json
        from fkcore import flow
        _r, lk = self.run_look()
        self.assertFalse([n for n in lk.notes if "since" in n])     # no build has said: quiet
        files = flow._source_files(self.dir)
        os.makedirs(os.path.join(self.dir, "out"), exist_ok=True)
        with open(os.path.join(self.dir, "out", "layout-source.json"), "w") as fh:
            json.dump({"files": dict(files, **{"gears.fk": "0" * 40})}, fh)
        _r, lk = self.run_look()
        self.assertEqual((lk.ok, lk.designed), (120, 120))        # the verdicts are the .fkp's
        said = [n for n in lk.notes if "since" in n]
        self.assertEqual(len(said), 1, lk.notes)
        self.assertIn("gears.fk changed since gears.fkp was written", said[0])
        self.assertIn("note: gears.fk changed", "\n".join(lk.lines()))

    def test_the_applied_design_is_ok_n_of_n_and_renders_the_same(self):
        lk = self.report()
        self.assertEqual((lk.ok, lk.designed), (120, 120))
        self.assertEqual(lk.rep.counts(), {"ok": 120})
        lines, differ = look.side_by_side(lk.design, lk.live, AREA)
        self.assertEqual(differ, 0)
        self.assertEqual(lk.design, lk.live)                      # look parity
        text = "\n".join(lk.lines())
        self.assertIn("ok 120/120 designed entities (notify all", text)
        self.assertIn("0 tiles differ", text)
        row = next(l for l in lines if l.startswith("  422 "))    # the drill row, both renders
        self.assertEqual(row.split(" | ")[0][6:], row.split(" | ")[1])

    def test_foreign_belts_are_marked_kept_and_strict_says_nobody(self):
        lk = self.report(self.foreign)
        marked = [v for v in lk.rep.verdicts if v.verdict == "marked"]
        self.assertEqual(len(marked), 2)
        temp = next(v for v in marked if (v.x, v.y) == SANCTIONED)
        self.assertEqual((temp.actor, temp.action, temp.key),
                         ("Rory_618", "mark", f"lab:mark/Rory_618@{TICK}"))
        kept = next(v for v in marked if (v.x, v.y) != SANCTIONED)
        self.assertEqual((kept.actor, kept.action), ("unknown", "keep"))
        marks = {m.name: m.until for m in lk.rep.marks}
        self.assertEqual(marks, {f"Rory_618@{TICK}": TICK + 2 * 3600 * 60,
                                 f"unknown@{TICK}": None})
        self.assertTrue(any("looks like a fix" in c for c in lk.rep.changes))
        self.assertEqual(lk.ok, 120)                              # the design is untouched
        strict = self.report(self.foreign, watch="strict")
        self.assertEqual(strict.rep.counts().get("unowned"), 2)
        self.assertEqual((strict.rep.marks, strict.policy["plots"]), ([], "strict"))
        self.assertIn("  unowned  transport-belt 307.5,430.5: unattributed (strict) by Rory_618",
                      strict.lines())

    def test_a_render_shows_the_foreign_belt_where_it_stands(self):
        lk = self.report(self.foreign)
        _lines, differ = look.side_by_side(lk.design, lk.live, AREA)
        self.assertEqual(differ, 2)
        row = lk.live.split("\n")[int(SANCTIONED[1]) - AREA[1]]
        self.assertEqual(row[int(SANCTIONED[0]) - AREA[0]], ">")

    def test_notify_all_pushes_each_change_once_nearby_and_off_do_not(self):
        r, lk = self.run_look(self.foreign)                       # the surface file says all
        self.assertEqual(len(lk.pushed), 2)
        self.assertEqual(len(r.said()), 2)
        self.assertTrue(all("[fk lab] transport-belt at " in c for c in r.said()))
        inbox = self.inbox()
        self.assertEqual(len(inbox), 2)
        self.assertTrue(inbox[0].startswith(f"{TICK} look: transport-belt at "))
        self.assertIn("notify all: pushed 2 line(s)", "\n".join(lk.lines()))
        for mode in ("nearby", "off"):
            r, lk = self.run_look(self.foreign, notify=mode)
            self.assertEqual((lk.pushed, r.said()), ([], []), mode)
            self.assertEqual(len(lk.rep.changes), 2)              # still in this look's report
            self.assertIn(f"notify {mode}: nothing pushed", "\n".join(lk.lines()))
        self.assertEqual(len(self.inbox()), 2)

    def test_written_marks_make_the_next_look_quiet(self):
        _r, lk = self.run_look(self.foreign, write_marks=True)
        self.assertEqual(lk.wrote, 2)
        lay = fkp.load(os.path.join(self.dir, "lab.fkp"))
        self.assertEqual(sorted(lay.marks), [f"Rory_618@{TICK}", f"unknown@{TICK}"])
        r, again = self.run_look(self.foreign)
        self.assertEqual(again.rep.counts(), {"ok": 120, "marked": 2})
        self.assertEqual((again.rep.marks, again.rep.changes, again.pushed, r.said()),
                         ([], [], [], []))

    def test_one_actor_kept_and_marked_writes_two_marks(self):
        # the lab look of 2026-10-20: both belts placed through RCON, so both are 'unknown'
        both = [dict(row) for row in self.foreign]
        both[0].pop("lu")
        _r, lk = self.run_look(both, write_marks=True)
        lay = fkp.load(os.path.join(self.dir, "lab.fkp"))
        self.assertEqual(sorted(lay.marks), [f"unknown@{TICK}", f"unknown@{TICK}.2"])
        self.assertEqual(lay.marks[f"unknown@{TICK}"].until, None)              # kept
        r, again = self.run_look(both)
        self.assertEqual((again.rep.counts(), again.rep.changes, r.said()),
                         ({"ok": 120, "marked": 2}, [], []))

    def test_fair_play_a_play_look_needs_an_area(self):
        path = os.path.join(self.dir, "lab.surface")
        with open(path, encoding="utf-8") as fh:
            text = fh.read().replace("\nfree\n", "\n")       # 3.1: not free, so fair play applies
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        with mock.patch.object(link, "snapshot", lambda *a, **k: self.fail("no snapshot")):
            with self.assertRaises(look.LookError):
                look.run(FakeRcon(), self.dir, CAT)
        _r, lk = self.run_look()                                  # with an area it looks
        self.assertEqual(lk.ok, 120)

    def test_a_lab_look_without_an_area_covers_the_design(self):
        r = FakeRcon()
        areas = []

        def snap(_r, _surface, area, tag="snap", keep=True):
            self.assertFalse(keep)                                # a look leaves no file
            areas.append(tuple(area))
            return capture(self.s, area)
        with mock.patch.object(link, "snapshot", snap):
            lk = look.run(r, self.dir, CAT)
        self.assertEqual(areas, [(308, 419, 346, 443)])           # every entity's tiles + 2
        self.assertEqual((lk.ok, lk.designed), (120, 120))

    def unpaired_lines(self, extra):
        return [line for line in self.report(extra).lines() if "UNPAIRED" in line]

    def test_a_built_underground_pair_is_not_unpaired(self):
        pair = [ug(305.5, 430.5, "input"), ug(308.5, 430.5, "output")]
        self.assertEqual(self.unpaired_lines(pair), [])
        self.assertEqual(self.report(pair).unpaired, [])

    def test_two_ends_that_point_the_same_way_never_form_a_tunnel(self):
        # the second lead run's mall: six outputs placed, no input among them
        lines = self.unpaired_lines([ug(305.5, 430.5, "output"),
                                     ug(308.5, 430.5, "output")])
        self.assertEqual(lines, [
            "  UNPAIRED underground-belt 305.5,430.5 (output; no partner within 5 tiles)",
            "  UNPAIRED underground-belt 308.5,430.5 (output; partner at 305.5,430.5 is "
            "another output, so it points the same way)"])
        lk = self.report([ug(305.5, 430.5, "output"), ug(308.5, 430.5, "output")])
        self.assertFalse(any(v.verdict == "UNPAIRED" for v in lk.rep.verdicts))
        self.assertEqual((lk.ok, lk.designed), (120, 120))         # a warning, never a gate

    def test_a_lone_built_end_is_unpaired_with_its_position(self):
        self.assertEqual(self.unpaired_lines([ug(305.5, 446.5, "input")]),
                         ["  UNPAIRED underground-belt 305.5,446.5 (input; no partner within "
                          "5 tiles)"])

    def test_a_ghost_pair_is_not_built_and_is_not_unpaired(self):
        self.assertEqual(self.unpaired_lines([ug(305.5, 430.5, "input", ghost=True),
                                              ug(308.5, 430.5, "output", ghost=True)]), [])

    def test_a_ghost_is_no_partner_for_a_built_end(self):
        self.assertEqual(self.unpaired_lines([ug(305.5, 430.5, "input"),
                                              ug(308.5, 430.5, "output", ghost=True)]),
                         ["  UNPAIRED underground-belt 305.5,430.5 (input; no partner within "
                          "5 tiles)"])

    def test_the_games_pair_truth_is_trusted(self):
        # the game paired the western output (as its `pair` says), so only the eastern one warns
        lines = self.unpaired_lines([ug(305.5, 430.5, "output", pair=(308.5, 430.5)),
                                     ug(308.5, 430.5, "output")])
        self.assertEqual(lines, [
            "  UNPAIRED underground-belt 308.5,430.5 (output; partner at 305.5,430.5 is "
            "another output, so it points the same way)"])

    def test_policy_overrides(self):
        sf = surfacemod.loads("surface lab\nfree\nforce lab\nwatch sanctioned: mark 2h\n")
        self.assertEqual(look.policy(sf), {"plots": "keep", "sanctioned": "mark 2h",
                                           "notify": "all"})
        self.assertEqual(look.policy(sf, "nearby", "plots=revert,sanctioned=mark 30min"),
                         {"plots": "revert", "sanctioned": "mark 30min", "notify": "nearby"})
        for bad in ("loud", "roads=keep", "plots="):
            with self.assertRaises(look.LookError):
                look.policy(sf, watch=bad)

    def test_wide_renders_stack(self):
        lines, differ = look.side_by_side("^>\nv<", "^>\nvv", (0, 0, 2, 2), max_width=8)
        self.assertEqual(differ, 1)
        self.assertEqual(lines[1:], ["design:", "    0 ^>", "    1 v<", "live:", "    0 ^>",
                                     "    1 vv"])


if __name__ == "__main__":
    unittest.main()
