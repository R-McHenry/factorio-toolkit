"""2.0.5 TURNED: a factory built over another keeps the old one's belts where the names match,
facing the old ways; on uncharted ground the paste turns nothing, so the apply lays them fresh.

The 2.0 run (20261022-1036-lead-v2) built its south factory (``south.fkp``: the 24-furnace
SmelterArray ``ism``, its drills ``iore`` and their routes) over the burner iron block it replaced
(``iron.fkp``, plot 17,83). Both files are the run's own, in ``tests/data/south-over-iron``. The
map is uncharted (no radar, no character), so ``build_blueprint`` places nothing there and every
row goes through the single-ghost fallback, which took a same-name entity on a row's position as
placed whichever way it faced. The diff after four builds: 26 belts and one inserter of the old
block on south's tiles, facing the old block's ways (``DRIFT faces 12, designed 4``): the drills'
ore belt ran west into a pole, the array's feed belts turned east and west mid-column, the coal
splitter fed a belt facing south. 17 more of the old block's belts had stood there too: their old
items didn't fit their new net, so the 1.2 rule (``renet`` with ``WRONG_ITEM``) laid them fresh;
these 26 held what their new net carries (ore on the ore belts, coal on the fuel belts) or
nothing.
"""
import copy
import os
import unittest
from unittest import mock

from fkcore import apply as applymod, compose, fkp, link, scene, sense
from fkcore import own as ownmod
from fkcore.catalog import Catalog

CAT = Catalog.load()
DATA = os.path.join(os.path.dirname(__file__), "data", "south-over-iron")
WATCH = {"plots": "keep", "sanctioned": "mark 2h", "notify": "nearby"}
AREA = [-10, 68, 72, 126]

#: what the old block's belts held, by its nets (iron.fk: ore_, fuel, plates)
OLD_ITEMS = {"iron/ore_": ["iron-ore"], "iron/fuel": ["coal"], "iron/plates": ["iron-plate"]}
#: south.fk's nets the turned and relaid belts are on, and what they carry
NEW_ITEMS = {"south/fuel": ["coal"], "south/ore_i": ["iron-ore"], "south/fe": ["iron-plate"],
             "south/cbo": ["electronic-circuit"]}

#: the live diff's turned entities (game/out/diff.txt, 2026-10-22 13:46), all the old block's
LIVE_TURNED = {
    "iore/outb0", "iore/outb1", "iore/outb2", "iore/outb3", "iore/outb4", "iore/outb5",
    "iore/outb6", "iore/outb7", "iore/outb8", "iore/outb9", "iore/outb10",
    "ism/feed0e14", "ism/feed0e15", "ism/feed0e16", "ism/feed0e23", "ism/feed0m2", "ism/o15",
    "ism/out0b21", "~fe/b69", "~fuel/b19", "~fuel/b20", "~fuel/b21", "~fuel/b22", "~fuel/b23",
    "~ore_i/b39", "~ore_i/b40"}


def composed(plot, module, at, size):
    with open(os.path.join(DATA, f"{module}.fkp"), encoding="utf-8") as fh:
        lay = fkp.loads(fh.read())
    return compose.compose(fkp.loads(f"fkp 1 surface nauvis\nplot {plot} at {at} rot 0 size "
                                     f"{size} module={module}\n"), {plot: lay}, CAT)


def local(key):
    return key.split(":", 1)[-1].split("/", 1)[1]


class World:
    """The uncharted map, as far as an apply sees it: the paste places nothing; an order out
    marks a built entity (a ghost ordered out goes at once); single ghosts stand where placed."""

    def __init__(self, s, items=None):
        self.things, self.orders, self.alone = [], [], []
        for e in s.entities.values():
            self.add(e.name, e.x, e.y, e.dir or 0, ghost=False,
                     ug={"in": "input", "out": "output"}.get(e.attrs.get("ug")),
                     items=(items or {}).get(sense._net(e)))

    def add(self, name, x, y, d, ghost, ug=None, items=None):
        tiles = CAT.tiles(name, float(x), float(y), d)
        xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
        row = {"n": name, "t": CAT.kind(name), "x": float(x), "y": float(y), "d": d, "g": ghost,
               "dc": False, "force": "player",
               "box": [min(xs) + 0.1, min(ys) + 0.1, max(xs) + 0.9, max(ys) + 0.9]}
        if ug:
            row["ug"] = ug
        if items and row["t"] in ("transport-belt", "underground-belt", "splitter"):
            row["it"] = {i: 1 for i in items}          # what the snapshot reads off a belt
        self.things.append(row)

    def lua(self, body):
        return "0"

    def paste(self, r, surface, force, bp, at, chunk=None):
        return "0"                      # build_blueprint on uncharted ground: nothing placed

    def snapshot(self, r, surface_name, area, tag="snap"):
        return {"tick": 1, "area": list(area), "things": copy.deepcopy(self.things)}

    def decon(self, r, surface, force, things):
        self.orders.append(list(things))
        for name, x, y in things:
            for t in list(self.things):
                if (t["n"], t["x"], t["y"]) == (name, float(x), float(y)):
                    if t["g"]:
                        self.things.remove(t)
                    else:
                        t["dc"] = True
        return len(things)

    def ghosts(self, r, surface, force, entities, wires=(), chunk=None):
        for e in entities:
            self.alone.append(e)
            self.add(e["name"], e["position"]["x"], e["position"]["y"], e.get("direction", 0),
                     ghost=True, ug=e.get("type"))
        return {"n": len(entities), "missed": {}}

    def robots(self):
        """Robots finish: what was ordered out is taken up, every ghost is built."""
        self.things = [t for t in self.things if not (t["dc"] and not t["g"])]
        for t in self.things:
            t["g"] = False


class TurnedTest(unittest.TestCase):
    def setUp(self):
        self.new = composed("south", "south", "-10,68", "82x58")
        self.old = composed("iron", "iron", "17,83", "27x26")
        self.own = ownmod.rows_of(self.old)          # the old block: the toolkit's own pasting

    def sense_old_block(self):
        live = scene.from_capture(World(self.old, OLD_ITEMS).snapshot(None, "nauvis", AREA))
        return sense.sense(self.new, live, CAT, AREA, WATCH, net_items=NEW_ITEMS, own=self.own)

    def test_the_old_blocks_belts_stand_turned_on_the_new_ones_tiles(self):
        rep = self.sense_old_block()
        turned = {local(v.key) for v in rep.verdicts if v.turned}
        relaid = {local(v.key) for v in rep.verdicts if v.renet and v.wrong_items}
        # every turned one is a DRIFT that says how it faces, and a belt or an inserter
        self.assertEqual(len(turned), 43)
        self.assertTrue(all(v.verdict == "DRIFT" and v.detail.startswith("faces ")
                            for v in rep.verdicts if v.turned))
        self.assertIn("faces 12, designed 4; TURNED", str(next(
            v for v in rep.verdicts if v.key == "nauvis:south/iore/outb0")))
        # the 1.2 rule laid fresh the 17 whose old items their new net doesn't carry; the live
        # world's 26 are exactly the rest
        self.assertEqual(len(relaid & turned), 17)
        self.assertEqual(turned - relaid, LIVE_TURNED)

    def run_apply(self, world, own):
        with mock.patch.object(link, "snapshot", world.snapshot), \
                mock.patch.object(link, "paste", world.paste), \
                mock.patch.object(link, "ghosts", world.ghosts), \
                mock.patch.object(applymod, "_decon", world.decon):
            return applymod.apply(world, self.new, CAT, mode="play", policy=WATCH,
                                  net_items=NEW_ITEMS, own=own)

    def test_an_apply_on_uncharted_ground_lays_the_turned_ones_fresh(self):
        world = World(self.old, OLD_ITEMS)
        rep = self.run_apply(world, self.own)
        self.assertEqual(rep.pasted, 0)                          # uncharted: the paste is refused
        # the 17 with old items went before the paste (1.2); the 26 the paste left turned go now
        self.assertEqual(len([v for v in rep.relaid if v.turned]), 17)
        self.assertEqual({local(k) for k in rep.turned}, LIVE_TURNED)
        turned_order = world.orders[-1]
        self.assertEqual(len(turned_order), 26)
        self.assertIn(("transport-belt", 23.5, 104.5), turned_order)     # iore/outb0
        # each gets its single ghost, facing as designed
        alone = {(e["name"], e["position"]["x"], e["position"]["y"]): e for e in world.alone}
        design = {(e.name, float(e.x), float(e.y)): e for e in self.new.entities.values()}
        for name, x, y in turned_order:
            self.assertEqual(alone[(name, x, y)].get("direction", 0),
                             design[(name, x, y)].dir or 0, (name, x, y))
        self.assertIn("TURNED 26 stood on their design tiles facing another way",
                      "\n".join(rep.lines()))
        # robots take the old ones up and build the ghosts: the next diff has nothing turned, and
        # the next apply orders nothing out for a turn
        world.robots()
        live = scene.from_capture(world.snapshot(None, "nauvis", AREA))
        after = sense.sense(self.new, live, CAT, AREA, WATCH, net_items=NEW_ITEMS, own=rep.own)
        self.assertEqual([v.key for v in after.verdicts if v.turned], [])
        self.assertEqual(self.run_apply(world, rep.own).turned, [])

    def test_where_the_paste_lands_it_turns_them_itself(self):
        # charted ground (a laptop test server, 2.0.77): a belt, an inserter or a splitter is
        # turned in place, one a quarter turn off gets a ghost and is ordered out
        cap = {"things": [
            {"n": "transport-belt", "x": 0.5, "y": 0.5, "d": 4, "g": False, "dc": False},
            {"n": "transport-belt", "x": 1.5, "y": 0.5, "d": 0, "g": False, "dc": True},
            {"n": "transport-belt", "x": 1.5, "y": 0.5, "d": 4, "g": True}]}
        rows = [{"src": f"t/b{i}", "name": "transport-belt", "x": i + 0.5, "y": 0.5,
                 "direction": 4, "attrs": {}} for i in range(2)]
        self.assertEqual(applymod.turned_rows(rows, cap, CAT), [])

    def test_what_counts_as_turned(self):
        rows = [
            {"src": "t/b0", "name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4,
             "attrs": {}},
            {"src": "t/u0", "name": "underground-belt", "x": 1.5, "y": 0.5, "direction": 4,
             "attrs": {"ug": "out"}},
            {"src": "t/i0", "name": "inserter", "x": 2.5, "y": 0.5, "direction": 8, "attrs": {}},
            {"src": "t/b1", "name": "transport-belt", "x": 3.5, "y": 0.5, "direction": 4,
             "attrs": {}},
            {"src": "t/g0", "name": "steam-engine", "x": 10.5, "y": 2.5, "direction": 0,
             "attrs": {}},
            {"src": "t/b2", "name": "transport-belt", "x": 4.5, "y": 0.5, "direction": 4,
             "attrs": {}}]
        cap = {"things": [
            {"n": "transport-belt", "x": 0.5, "y": 0.5, "d": 12, "g": False, "dc": False},
            # the other underground end, facing the same way
            {"n": "underground-belt", "x": 1.5, "y": 0.5, "d": 4, "ug": "input", "g": False},
            {"n": "inserter", "x": 2.5, "y": 0.5, "d": 0, "g": False},
            # as designed
            {"n": "transport-belt", "x": 3.5, "y": 0.5, "d": 4, "g": False},
            # a turned steam engine stays a DRIFT to read: a power plant is not taken up for it
            {"n": "steam-engine", "x": 10.5, "y": 2.5, "d": 4, "g": False},
            # a ghost an earlier build left, of an older design
            {"n": "transport-belt", "x": 4.5, "y": 0.5, "d": 8, "g": True}]}
        self.assertEqual(applymod.turned_rows(rows, cap, CAT), [0, 1, 2, 5])
        # a snapshot that doesn't read a direction judges none
        bare = {"things": [{k: v for k, v in t.items() if k != "d"} for t in cap["things"]]}
        self.assertEqual(applymod.turned_rows(rows, bare, CAT), [1])

    def test_a_belt_a_player_turned_is_a_hand_edit(self):
        # Rory's rule (2.0): the source wins, so the build turns it back, and says so
        live = scene.from_capture(World(self.old, OLD_ITEMS).snapshot(None, "nauvis", AREA))
        belt = next(t for t in live["things"] if (t["x"], t["y"]) == (23.5, 104.5))
        belt["last_user"] = "Rory_618"
        rep = sense.sense(self.new, live, CAT, AREA, WATCH, net_items=NEW_ITEMS, own=self.own)
        self.assertEqual(
            [line for line in sense.hand_edits(rep) if "turned" in line],
            ["Rory_618 turned transport-belt at 23.5,104.5 (south/iore/outb0: faces 12, designed "
             "4); this build lays it fresh as designed"])

    def test_the_diff_says_turned(self):
        from types import SimpleNamespace
        from fkcore import flow
        rep = self.sense_old_block()
        ctx = SimpleNamespace(surface=SimpleNamespace(name="nauvis", mode="play"))
        check = flow._turned(ctx, rep)
        self.assertEqual(check.code, "TURNED")
        self.assertTrue(check.msg.startswith(
            "43 inserter, transport-belt, underground-belt stand on their design tiles facing "
            "another way or as the other underground end, so their lines stop there (south/iore/"
            "outb0 (faces 12, designed 4), "), check.msg)
        self.assertIn("the apply lays them fresh as designed", check.msg)
        self.assertIsNone(flow._turned(ctx, SimpleNamespace(verdicts=[])))


if __name__ == "__main__":
    unittest.main()
