"""sense(area) against fixture scenes only (no game): verdicts, attribution, marks, keep."""
import copy
import unittest

from fkcore import compose, fkp, scene, sense
from fkcore.catalog import Catalog
from tests.test_fkp import MINI

CAT = Catalog.load()
SURFACE = """\
fkp 1 surface nauvis
cover robots robots
plot mini at 10,0 rot 0 size 7x7
claim boom-test box 30,0 35,5 until 4500000 "explosives trial"
mark Rory_618@4000000 tiles 40,0 40,1 until 4100000
e robots/r0 roboport 2,10
"""
WATCH = {"plots": "keep", "sanctioned": "mark 2h", "notify": "nearby"}
NETS = {"mini/iron": ["iron-plate"], "mini/gear": ["iron-gear-wheel"]}
AREA = [0, -2, 50, 14]
TICK = 4200000


def surface():
    return compose.compose(fkp.loads(SURFACE), {"mini": fkp.loads(MINI)}, CAT)


def live_as_designed(s):
    """A live scene that holds exactly the design (what a finished apply leaves)."""
    d = scene.design_scene(s, CAT)
    things = []
    for t in d["things"]:
        t = dict(t)
        t["src"] = t["design"] = None          # the world has no keys: matching is by position
        things.append(t)
    return scene.scene("live", things, tick=TICK, area=AREA)


def find(live, name, x, y):
    return next(t for t in live["things"] if (t["name"], t["x"], t["y"]) == (name, x, y))


def verdicts(rep):
    return {(v.verdict, v.key or v.name) for v in rep.verdicts if v.verdict != "ok"}


class HandEditsTest(unittest.TestCase):
    """2.0 (Rory, 2026-10-21: a human's change is reported, not protected)."""

    def test_a_foreign_thing_the_apply_removes(self):
        s = surface()
        live = copy.deepcopy(live_as_designed(s))
        live["things"].append(scene.thing(name="wooden-chest", type="container", x=45.5, y=2.5,
                                          last_user="Rory_618"))
        rep = sense.sense(s, live, CAT, AREA, {"plots": "keep", "sanctioned": "revert"})
        self.assertEqual(sense.hand_edits(rep), [
            "Rory_618 placed wooden-chest at 45.5,2.5, which the design doesn't have; this build "
            "removes it"])
        kept = sense.sense(s, live, CAT, AREA, WATCH)            # mark 2h: it stays, unsaid
        self.assertEqual(sense.hand_edits(kept), [])


class SenseTest(unittest.TestCase):
    def setUp(self):
        self.s = surface()
        self.live = live_as_designed(self.s)

    def run_sense(self, live=None, area=AREA, watch=WATCH):
        return sense.sense(self.s, live or self.live, CAT, area, watch, net_items=NETS)

    def test_the_design_built_is_all_ok(self):
        rep = self.run_sense()
        self.assertEqual(rep.counts(), {"ok": 20})       # 19 mini entities + the roboport
        self.assertEqual((rep.changes, rep.marks, rep.push), ([], [], []))

    def test_layout_verdicts(self):
        live = copy.deepcopy(self.live)
        live["things"].remove(find(live, "transport-belt", 10.5, 0.5))           # MISSING
        find(live, "transport-belt", 11.5, 0.5)["ghost"] = True                  # GHOST
        find(live, "fast-inserter", 11.5, 1.5)["direction"] = 0                  # DRIFT (dir)
        find(live, "assembling-machine-1", 14.5, 3.5)["recipe"] = "pipe"         # DRIFT (recipe)
        find(live, "underground-belt", 13.5, 0.5)["ug"] = "input"               # DRIFT (ug)
        find(live, "transport-belt", 14.5, 0.5)["items"] = {"copper-plate": 3}   # WRONG_ITEM
        belt = find(live, "transport-belt", 15.5, 0.5)                          # WRONG
        belt.update(name="iron-chest", type="container")
        rep = self.run_sense(live)
        self.assertEqual(verdicts(rep), {
            ("not-placed", "nauvis:mini/~iron/b0"), ("ghost", "nauvis:mini/~iron/b1"),
            ("settings-changed", "nauvis:mini/gears/i0"), ("settings-changed", "nauvis:mini/gears/m1"),
            ("settings-changed", "nauvis:mini/~iron/u1"), ("other-entity", "nauvis:mini/~iron/b3"),
            ("conflict", "nauvis:mini/~iron/b3")})
        wrong = next(v for v in rep.verdicts if v.wrong_items)
        self.assertEqual((wrong.key, wrong.wrong_items), ("nauvis:mini/~iron/b2", ["copper-plate"]))
        drift = {v.key: v.detail for v in rep.verdicts if v.verdict == "settings-changed"}
        self.assertEqual(drift["nauvis:mini/gears/i0"], "faces 0, designed 8")
        self.assertEqual(drift["nauvis:mini/gears/m1"],
                         "recipe pipe, designed iron-gear-wheel")
        self.assertEqual(drift["nauvis:mini/~iron/u1"], "underground input, designed output")
        # 3.1: the chest standing where a belt belongs is a MISMATCH the toolkit did not paste
        # (no mark, not pasted over); its owner is unknown (no last_user, no placement)
        self.assertEqual(rep.marks, [])
        wrong = next(v for v in rep.verdicts if v.verdict == "other-entity")
        self.assertEqual(wrong.owner, "unknown")
        self.assertTrue(any(c.startswith("iron-chest at 15.5,0.5: on mini/~iron/b3's tile, unknown "
                                         "(plots): MISMATCH") for c in rep.changes), rep.changes)
        (c,) = sense.conflicts(rep)
        self.assertEqual((c.key, c.stands, c.owner), ("nauvis:mini/~iron/b3", "iron-chest", "unknown"))
        self.assertIn("fk register 15,0,16,1 MODULE", c.resolve)

    def test_a_belt_rory_places_in_sanctioned_space_is_marked_temp(self):
        live = copy.deepcopy(self.live)
        live["things"].append(scene.thing(name="transport-belt", type="transport-belt", x=25.5,
                                          y=3.5, direction=4, last_user="Rory_618"))
        rep = self.run_sense(live)
        (mark,) = rep.marks
        self.assertEqual((mark.name, mark.tiles, mark.until),
                         ("Rory_618@4200000", [(25, 3)], 4200000 + 2 * 3600 * 60))
        v = next(v for v in rep.verdicts if v.verdict == "marked")
        self.assertEqual(v.detail, "TEMP Rory_618, marked for 2h")
        self.assertEqual(rep.changes, ["transport-belt at 25.5,3.5: built by Rory_618 "
                                       "(sanctioned, mark)"])
        self.assertEqual(rep.push, [])                   # notify nearby: this look only

    def test_a_belt_in_a_plot_next_to_a_net_is_kept_and_offered_for_adopt(self):
        live = copy.deepcopy(self.live)
        live["things"].append(scene.thing(name="transport-belt", type="transport-belt", x=16.5,
                                          y=1.5, direction=8, last_user="Rory_618"))
        rep = self.run_sense(live)
        (mark,) = rep.marks
        self.assertIsNone(mark.until)                    # keep: until its owner decides
        self.assertIn("next to net mini/iron: looks like a fix to it", rep.changes[0])
        self.assertEqual(rep.owners[len(live["things"]) - 1], "nauvis:mark/Rory_618@4200000")

    def test_a_kept_fix_is_adopted_and_then_sensed_ok(self):
        from fkcore import adopt
        live = copy.deepcopy(self.live)
        fix = scene.thing(name="transport-belt", type="transport-belt", x=16.5, y=1.5,
                          direction=8, last_user="Rory_618")
        live["things"].append(fix)
        rep = self.run_sense(live)
        (mark,) = rep.marks
        surface_lay = fkp.loads(SURFACE)
        surface_lay.marks[mark.name] = mark
        mini = fkp.loads(MINI)
        keys, covered = adopt.adopt(mini, surface_lay.plots["mini"], [fix], "iron", CAT,
                                    surface_lay.marks)
        self.assertEqual((keys, covered), (["~iron/a0"], [mark.name]))
        self.assertEqual(fkp.invariants(mini, CAT), [])
        for name in covered:
            del surface_lay.marks[name]
        s = compose.compose(surface_lay, {"mini": mini}, CAT)
        again = sense.sense(s, live, CAT, AREA, WATCH, net_items=NETS)
        self.assertEqual(again.counts(), {"ok": 21})          # the fix is design now
        self.assertEqual((again.marks, again.changes), ([], []))
        with self.assertRaises(adopt.AdoptError):
            adopt.adopt(mini, surface_lay.plots["mini"],
                        [scene.thing(name="iron-chest", x=16.5, y=3.5)], "iron", CAT)

    def test_one_actors_keep_and_mark_in_one_look_are_two_marks(self):
        # found live on the lab (2026-10-20): both were named unknown@<tick>, so writing them
        # into the surface .fkp kept only one, and the kept fix came back as a new change
        live = copy.deepcopy(self.live)
        live["things"] += [scene.thing(name="transport-belt", x=25.5, y=3.5),        # sanctioned
                           scene.thing(name="transport-belt", x=16.5, y=1.5, direction=8)]  # plot
        rep = self.run_sense(live)
        self.assertEqual([(m.name, m.until) for m in rep.marks],
                         [("unknown@4200000", None), ("unknown@4200000.2", 4200000 + 432000)])
        keys = {v.key for v in rep.verdicts if v.verdict == "marked"}
        self.assertEqual(keys, {"nauvis:mark/unknown@4200000", "nauvis:mark/unknown@4200000.2"})
        surface_lay = fkp.loads(SURFACE)
        for m in rep.marks:
            surface_lay.marks[m.name] = m
        s = compose.compose(fkp.loads(fkp.dumps(surface_lay)), {"mini": fkp.loads(MINI)}, CAT)
        again = sense.sense(s, live, CAT, AREA, WATCH, net_items=NETS)
        self.assertEqual((again.counts(), again.marks, again.changes),
                         ({"ok": 20, "marked": 2}, [], []))
        self.assertEqual({v.actor for v in again.verdicts if v.verdict == "marked"}, {"unknown"})
        # a name the surface already holds is not reused either
        surface_lay = fkp.loads(SURFACE + "mark unknown@4200000 tiles 45,13\n")
        s = compose.compose(surface_lay, {"mini": fkp.loads(MINI)}, CAT)
        rep = sense.sense(s, live, CAT, AREA, WATCH, net_items=NETS)
        self.assertEqual([m.name for m in rep.marks], ["unknown@4200000.2", "unknown@4200000.3"])

    def test_claims_existing_marks_expiry_enemies_and_nature(self):
        live = copy.deepcopy(self.live)
        extra = [scene.thing(name="iron-chest", x=31.5, y=1.5, last_user="computah"),     # claim
                 scene.thing(name="wooden-chest", x=40.5, y=0.5, last_user="Rory_618"),   # mark
                 scene.thing(name="small-biter", x=20.5, y=10.5, force="enemy"),
                 scene.thing(name="tree-01", x=22.5, y=11.5, force="neutral")]
        live["things"] += extra
        rep = self.run_sense(live)
        self.assertEqual(verdicts(rep), {("claimed", "nauvis:claim/boom-test"),
                                         ("marked", "nauvis:mark/Rory_618@4000000")})
        self.assertEqual(rep.expired, ["Rory_618@4000000"])     # until 4100000 < tick 4200000
        self.assertEqual(rep.marks, [])
        n = len(live["things"])
        self.assertEqual((rep.owners[n - 2], rep.owners[n - 1]), ("enemy", "nature"))

    def test_attention_only_the_area(self):
        live = copy.deepcopy(self.live)
        live["things"].append(scene.thing(name="transport-belt", x=45.5, y=12.5, last_user="x"))
        live["things"].remove(find(live, "transport-belt", 10.5, 0.5))
        rep = self.run_sense(live, area=[0, 5, 50, 14])          # the south half only
        self.assertNotIn("not-placed", rep.counts())                # the gap is outside the look
        self.assertEqual(len(rep.marks), 1)                      # the belt at 45,12 is inside

    def test_revert_strict_and_notify_all(self):
        live = copy.deepcopy(self.live)
        live["things"].append(scene.thing(name="transport-belt", x=25.5, y=3.5, last_user="Rory_618"))
        rep = self.run_sense(live, watch={"plots": "keep", "sanctioned": "revert",
                                          "notify": "all"})
        v = next(v for v in rep.verdicts if v.verdict == "unowned")
        self.assertEqual((v.action, v.detail), ("revert", "the next apply removes it"))
        self.assertEqual(rep.marks, [])
        self.assertEqual(rep.push, rep.changes)                  # lab mode: pushed
        rep = self.run_sense(live, watch={"plots": "keep", "sanctioned": "strict"})
        self.assertEqual(next(v for v in rep.verdicts if v.verdict == "unowned").action, "strict")

    def test_from_capture(self):
        dump = {"tick": 5, "area": [0, 0, 4, 4], "nests": [],
                "things": [{"n": "transport-belt", "t": "transport-belt", "x": 1.5, "y": 1.5,
                            "d": 4, "g": False, "force": "player", "it": {"iron-plate": 3},
                            "box": [1.1, 1.1, 1.9, 1.9], "lu": "Rory_618"}]}
        t = scene.from_capture(dump)["things"][0]
        self.assertEqual((t["tiles"], t["last_user"], t["items"], t["direction"]),
                         ([[1, 1]], "Rory_618", {"iron-plate": 3}, 4))

    def test_duration(self):
        self.assertEqual(sense.duration_ticks("2h"), 432000)
        self.assertEqual(sense.duration_ticks("30min"), 108000)
        with self.assertRaises(ValueError):
            sense.duration_ticks("soon")




class HalfTurnTest(unittest.TestCase):
    def test_a_straight_rail_turned_half_round_is_the_same_piece(self):
        # 2.1.32: a Literal at rot 2 designs its lane rails facing 12; the game stores 4
        self.assertEqual(sense.turn(CAT, "straight-rail", 12, None, 4, None), [])
        self.assertEqual(sense.turn(CAT, "straight-rail", 4, None, 0, None),
                         ["faces 0, designed 4"])
        self.assertEqual(sense.turn(CAT, "train-stop", 8, None, 0, None), ["faces 0, designed 8"])


if __name__ == "__main__":
    unittest.main()
