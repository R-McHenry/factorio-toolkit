"""fkcore.own (1.2): the toolkit's own entities, what the applies pasted. The 0534 run kept its own
dropped rows under ``watch plots: keep``, left a moved plot's 166 entities standing as MARKED
outside every plot, and an emptied factory's 28 ghosts; the record makes them NOBODY."""
import copy
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import apply as applymod, fkp, flow, link, own, scene, sense
from fkcore.catalog import Catalog
from tests.test_fkp import MINI
from tests.test_sense import AREA, NETS, SURFACE, WATCH, live_as_designed, surface

CAT = Catalog.load()
OLD_BELT = own.Row("nauvis:mini/~old/b0", "transport-belt", 16.5, 1.5, 4, "mini/old")
OLD_GHOST = own.Row("nauvis:mini/old/m0", "assembling-machine-1", 25.5, 3.5, None, None)


def record_of(s, *extra):
    rec = own.rows_of(s)
    for row in extra:
        rec[own.at(row.name, row.x, row.y)] = row
    return rec


def with_old(live, belt_user=None):
    """The design built, plus the old belt (in the plot) and the old ghost (sanctioned)."""
    live = copy.deepcopy(live)
    live["things"] += [scene.thing(name="transport-belt", type="transport-belt", x=16.5, y=1.5,
                                   direction=4, last_user=belt_user),
                       scene.thing(name="assembling-machine-1", type="assembling-machine",
                                   x=25.5, y=3.5, tiles=[[x, y] for x in (24, 25, 26)
                                                         for y in (2, 3, 4)], ghost=True)]
    return live


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkown-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_the_seed_is_the_last_written_fkp_files(self):
        with open(os.path.join(self.dir, "nauvis.fkp"), "w", newline="\n") as fh:
            fh.write(SURFACE.replace("size 7x7", "size 7x7 module=mini"))
        with open(os.path.join(self.dir, "mini.fkp"), "w", newline="\n") as fh:
            fh.write(MINI)
        rec = own.seed(self.dir, "nauvis", CAT)
        self.assertEqual(len(rec), 20)                           # mini's 19 and the roboport
        belt = rec[own.at("transport-belt", 10.5, 0.5)]
        self.assertEqual((belt.key, belt.net), ("nauvis:mini/~iron/b0", "mini/iron"))
        self.assertIsNone(rec[own.at("roboport", 2, 10)].net)
        own.save(self.dir, "nauvis", rec)
        self.assertEqual(own.load(self.dir, "nauvis"), rec)
        self.assertEqual(own.seed(tempfile.gettempdir() + "/no-such-game", "nauvis", CAT), {})

    def test_an_apply_keeps_what_is_outside_and_what_still_stands(self):
        s = surface()
        far = own.Row("nauvis:mini/~old/b9", "transport-belt", 90.5, 3.5, 4, "mini/old")
        gone = own.Row("nauvis:mini/~old/b8", "transport-belt", 20.5, 9.5, 4, "mini/old")
        rec = record_of(s, OLD_BELT, far, gone)
        self.assertEqual({r.key for r in own.dropped(rec, s)},
                         {OLD_BELT.key, far.key, gone.key})
        after = own.update(rec, s, CAT, AREA, None, standing=[own.at("transport-belt", 16.5, 1.5)])
        self.assertIn(own.at("transport-belt", 90.5, 3.5), after)       # outside the scope
        self.assertIn(own.at("transport-belt", 16.5, 1.5), after)       # still stood: ordered out
        self.assertNotIn(own.at("transport-belt", 20.5, 9.5), after)    # gone already
        self.assertTrue(set(own.rows_of(s)) <= set(after))              # the design, pasted


class SenseTest(unittest.TestCase):
    def setUp(self):
        self.s = surface()
        self.live = with_old(live_as_designed(self.s))

    def run_sense(self, live, rec):
        return sense.sense(self.s, live, CAT, AREA, WATCH, net_items=NETS, own=rec)

    def test_without_the_record_they_are_kept(self):
        rep = self.run_sense(self.live, None)
        self.assertEqual(rep.counts().get("MARKED"), 2)

    def test_own_dropped_rows_are_nobody_whatever_the_policy(self):
        rep = self.run_sense(self.live, record_of(self.s, OLD_BELT, OLD_GHOST))
        nobody = {v.key: v for v in rep.verdicts if v.verdict == "NOBODY"}
        self.assertEqual(set(nobody), {OLD_BELT.key, OLD_GHOST.key})
        self.assertEqual({v.action for v in nobody.values()}, {"own"})
        self.assertEqual(rep.marks, [])                                  # nothing is kept
        self.assertIn("transport-belt at 16.5,1.5: the toolkit's own (nauvis:mini/~old/b0), "
                      "dropped from the design (plots); the next apply removes it", rep.changes)
        self.assertIn("a ghost of assembling-machine-1 at 25.5,3.5: the toolkit's own "
                      "(nauvis:mini/old/m0), dropped from the design (sanctioned); the next "
                      "apply removes it", rep.changes)

    def test_a_row_a_player_touched_is_a_foreign_change(self):
        live = with_old(live_as_designed(self.s), belt_user="Rory_618")
        rep = self.run_sense(live, record_of(self.s, OLD_BELT, OLD_GHOST))
        belt = next(v for v in rep.verdicts if v.x == 16.5 and v.y == 1.5)
        self.assertEqual((belt.verdict, belt.actor), ("MARKED", "Rory_618"))

    def test_a_claim_still_explains_it(self):
        live = copy.deepcopy(live_as_designed(self.s))
        live["things"].append(scene.thing(name="iron-chest", x=31.5, y=1.5))
        rec = record_of(self.s, own.Row("nauvis:kit/c0", "iron-chest", 31.5, 1.5))
        rep = self.run_sense(live, rec)
        self.assertIn("CLAIMED", rep.counts())
        self.assertNotIn("NOBODY", rep.counts())


class FakeRcon:
    """The game, as far as an apply asks: pastes, and decon orders counted."""

    def __init__(self):
        self.calls, self.ordered = [], []

    def lua(self, body):
        self.calls.append(body)
        if "order_deconstruction" in body:
            data = json.loads(json.loads(body.split("json_to_table(", 1)[1].split(")) do", 1)[0]))
            self.ordered += [tuple(t) for t in data]
            return str(len(data))
        return "0"


def snapshot_of(live):
    def snap(r, surface_name, area, tag="snap", keep=True):
        rows = []
        for t in live["things"]:
            row = {"n": t["name"], "t": t["type"], "x": t["x"], "y": t["y"], "d": t["direction"],
                   "g": t["ghost"], "force": t["force"]}
            if t.get("last_user"):
                row["lu"] = t["last_user"]
            xs, ys = [p[0] for p in t["tiles"]], [p[1] for p in t["tiles"]]
            row["box"] = [min(xs) + 0.1, min(ys) + 0.1, max(xs) + 0.9, max(ys) + 0.9]
            rows.append(row)
        return {"tick": 1, "area": list(area), "things": rows}
    return snap


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.s = surface()

    def run_apply(self, live, rec, area=None):
        r = FakeRcon()
        with mock.patch.object(link, "snapshot", snapshot_of(live)), \
                mock.patch.object(link, "paste", lambda *a, **k: "0"):
            rep = applymod.apply(r, self.s, CAT, area, mode="play", policy=WATCH,
                                 net_items=NETS, own=rec)
        return r, rep

    def test_the_apply_orders_its_own_dropped_rows_out_ghosts_too(self):
        live = with_old(live_as_designed(self.s))
        rec = record_of(self.s, OLD_BELT, OLD_GHOST)
        r, rep = self.run_apply(live, rec)
        self.assertEqual(sorted(r.ordered), [("assembling-machine-1", 25.5, 3.5),
                                             ("transport-belt", 16.5, 1.5)])
        self.assertEqual((rep.decon, rep.dropped), (2, 2))
        self.assertIn("2 NOBODY entities ordered for deconstruction (2 of them the toolkit's own, "
                      "dropped from the design)", "\n".join(rep.lines()))
        self.assertIn(own.at("transport-belt", 16.5, 1.5), rep.own)    # until robots took it
        # robots took them up: the next apply finds nothing, and the record forgets them
        r, rep = self.run_apply(live_as_designed(self.s), rep.own)
        self.assertEqual((r.ordered, rep.dropped), ([], 0))
        self.assertEqual(set(rep.own), set(own.rows_of(self.s)))

    def test_a_moved_plot_s_old_ground_is_in_the_default_area(self):
        far = own.Row("nauvis:mini/~old/b9", "transport-belt", 90.5, 3.5, 4, "mini/old")
        rec = record_of(self.s, far)
        self.assertEqual(applymod.default_area(self.s, CAT, None, None)[2], 19)
        self.assertEqual(applymod.default_area(self.s, CAT, None, rec)[2], 93)
        live = copy.deepcopy(live_as_designed(self.s))
        live["things"].append(scene.thing(name="transport-belt", x=90.5, y=3.5, direction=4))
        r, rep = self.run_apply(live, rec)
        self.assertEqual(r.ordered, [("transport-belt", 90.5, 3.5)])
        self.assertEqual(rep.area[2], 93)

    def test_an_emptied_scope_still_takes_its_rows_up(self):
        live = with_old(live_as_designed(self.s))
        rec = record_of(self.s, OLD_BELT)
        r, rep = self.run_apply(live, rec, area=(16, 0, 18, 3))      # only the old belt's tile
        self.assertEqual(r.ordered, [("transport-belt", 16.5, 1.5)])

    def test_the_decon_list_finds_a_ghost_by_the_entity_it_stands_for(self):
        lua = link.lua_decon_list("nauvis", "player", [("assembling-machine-1", 25.5, 3.5)])
        self.assertIn("ghost_name = t[1]", lua)
        self.assertIn("type = 'entity-ghost'", lua)


class FlowSeedTest(unittest.TestCase):
    def test_write_layout_seeds_the_record_once(self):
        d = tempfile.mkdtemp(prefix="fkownflow-")
        self.addCleanup(shutil.rmtree, d, True)
        files = {"t.fk": "mine = MinerRow<n=1, resource=iron-ore> @(0, 0)\n"
                         "dst  = Chest<provider>                  @(20, 3)\n"
                         "net p: mine -> dst\n",
                 "nauvis.surface": "surface nauvis\nmode play\nterrain none\n"
                                   "place t = t plot 0,0 30x12\n",
                 "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\n"
                                     "place --keep pinned\nroute --only stale\nfloorplan\n"
                                     "write_layout\n"}
        for name, text in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        script = os.path.join(d, "nauvis.build.fkb")

        def build():
            code, ctx = flow.run(script, cat=CAT, echo=lambda _l: None)
            self.assertEqual(code, 0, ctx.log)
            with open(os.path.join(d, "out", "write_layout.txt"), encoding="utf-8") as fh:
                return fh.read()

        text = build()                                     # a new game: nothing written before
        self.assertIn("own: 0 entities of the last written .fkp files", text)
        self.assertNotIn("own:", build())                  # the record exists: never seeded again
        os.remove(own.path(d, "nauvis"))                   # a run from before 1.2
        text = build()
        rec = own.load(d, "nauvis")
        self.assertIn(f"own: {len(rec)} entities of the last written .fkp files", text)
        keys = {r.key for r in rec.values()}
        self.assertTrue({"nauvis:t/mine/m0", "nauvis:t/dst/c0", "nauvis:t/~p/i0"} <= keys, keys)
        self.assertEqual(rec[own.at("fast-inserter", *next(
            (r.x, r.y) for r in rec.values() if r.key == "nauvis:t/~p/i0"))].net, "t/p")


if __name__ == "__main__":
    unittest.main()
