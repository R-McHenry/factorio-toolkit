"""fkcore.avail (2.0.14): a design says ``any`` and the toolkit takes the tier it can build.

Rory, 2026-10-25: "The toolkit should let whatever inserter be easy to use, same with power poles.
Right now the bad habit is agents using lots of fast inserters when they only have regular
inserters." The 2026-10-25 run pasted 4 fast inserters needs-research (research at 81%, none in the network)
while 50 plain inserters sat in the kit, and the burner row they fed stood dead; its script had to
say ``route --hand inserter`` by hand, and a single ``Assembler<inserter=inserter>`` got fast hands
from the router anyway.

The choice: the best prototype robots can build now for what the design needs, else the best one it
can make, else the family's default. The snapshot is ``out/avail.json``, written on the game host
(``report_bom --stock live``, ``fk avail --save``) because the design half runs where there is no
game link.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from fkcore import avail, expand, flow, supply
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate
from fkcore.fragments import FragmentError
from fkcore.lang import parse

CAT = Catalog.load()
_TMP = [0]


def tmp(prefix="fkavail-"):
    """A scratch dir made here: a ``tempfile.mkdtemp()`` dir gets an ACL the DSH file sandbox
    denies (the workspace's STATE.md says so), a dir made under the temp root does not."""
    _TMP[0] += 1
    path = os.path.join(tempfile.gettempdir(), f"{prefix}{os.getpid()}-{_TMP[0]}")
    os.makedirs(path, exist_ok=True)
    return path


def gone(path):
    __import__("shutil").rmtree(path, ignore_errors=True)

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
SHOP_SCRIPT = """\
read_surface    mall
read_terrain    none
elaborate
place           --keep pinned
route           --only stale --effort normal --hand any
cover power     --pole any
report_checks
write_layout
"""


def row(name, stock=0, enabled=True, known=True):
    return {"entity": name, "item": name, "stock": stock, "known": known, "enabled": enabled}


def sup(*rows, tick=1):
    return supply.from_raw({"tick": tick, "force": "player", "surface": "nauvis", "networks": 1,
                            "entities": list(rows), "recipes": [], "research": {}})


#: the 2026-10-25 run: the kit's 50 plain inserters, fast inserters not researched, medium poles in
#: the kit (buildable because they are in the network), the small pole's recipe locked by wood
KIT = dict(inserter=row("inserter", 50), fast=row("fast-inserter", 0, enabled=False),
           medium=row("medium-electric-pole", 93, enabled=False), small=row("small-electric-pole", 0))


class ChooseTest(unittest.TestCase):
    def setUp(self):
        avail._snapshot = avail.Snapshot()
        avail._notes = []

    def tearDown(self):
        avail._snapshot = avail.Snapshot()
        avail._notes = []

    def test_a_hand_is_the_cheapest_rung_the_network_can_build(self):
        # 2.0.15 (Rory, 2026-10-25): "the default should probably be lowest, and it would go
        # higher if it senses a bottleneck". fkcore.hands raises the connectors that need more.
        avail.install(sup(KIT["inserter"], KIT["fast"]))
        got, note = avail.choose("hand", "any", need=4)
        self.assertEqual(got, "inserter")
        self.assertIn("hand=any: inserter", note)
        self.assertIn("the network holds 50", note)
        avail.install(sup(row("inserter", 0), row("fast-inserter", 30)))
        self.assertEqual(avail.choose("hand", "any", need=4)[0], "fast-inserter")

    def test_best_asks_for_the_other_end(self):
        avail.install(sup(KIT["inserter"], row("fast-inserter", 30)))
        self.assertEqual(avail.choose("hand", "best", need=2)[0], "fast-inserter")
        self.assertEqual(avail.choose("hand", "BEST", need=2)[0], "fast-inserter")
        self.assertTrue(avail.is_best("best"))
        self.assertFalse(avail.is_best("any"))

    def test_what_the_design_needs_is_what_it_must_hold(self):
        avail.install(sup(row("inserter", 30), row("fast-inserter", 40)))
        self.assertEqual(avail.choose("hand", "any", need=2)[0], "inserter")
        self.assertEqual(avail.choose("hand", "any", need=40)[0], "fast-inserter")   # 30 < 40

    def test_a_locked_tier_is_never_chosen_over_one_that_can_be_made(self):
        avail.install(sup(row("inserter", 0), row("fast-inserter", 0, enabled=False)))
        got, note = avail.choose("hand", "any", need=1)
        self.assertEqual(got, "inserter")
        self.assertIn("SHORT", note)

    def test_the_poles(self):
        avail.install(sup(KIT["medium"], KIT["small"]))
        self.assertEqual(avail.choose("pole", "any", need=10)[0], "medium-electric-pole")
        avail.install(sup(row("medium-electric-pole", 0, enabled=False),
                          row("small-electric-pole", 40)))
        got, note = avail.choose("pole", "any", need=10)
        self.assertEqual(got, "small-electric-pole")
        self.assertIn("pole=any: small-electric-pole", note)

    def test_when_nothing_can_be_built_a_makeable_tier_beats_an_unread_one(self):
        avail.install(sup(row("inserter", 0), row("fast-inserter", 0, enabled=False)))
        got, note = avail.choose("hand", "any", need=20)
        self.assertEqual(got, "inserter")
        self.assertIn("SHORT", note)
        avail.install(sup(row("small-electric-pole", 0)))       # medium not read at all
        got, note = avail.choose("pole", "any", need=20)
        self.assertEqual(got, "small-electric-pole")            # SHORT, so it can be made
        self.assertIn("SHORT", note)
        avail.install(sup(row("medium-electric-pole", 0, enabled=False),
                          row("small-electric-pole", 0, enabled=False)))
        got, note = avail.choose("pole", "any", need=20)
        self.assertEqual(got, "medium-electric-pole")           # LOCKED: the family's default
        self.assertIn("needs-research", note)

    def test_a_name_is_taken_as_given_and_the_words_are_aliases(self):
        avail.install(sup(KIT["inserter"], KIT["fast"]))
        self.assertEqual(avail.choose("hand", "fast-inserter"), ("fast-inserter", None))
        self.assertEqual(avail.choose("hand", "long-handed-inserter")[0], "long-handed-inserter")
        for word in ("any", "ANY", "auto", "whatever"):
            self.assertTrue(avail.is_any(word), word)
            self.assertEqual(avail.choose("hand", word, need=1)[0], "inserter")
        self.assertFalse(avail.is_any("inserter"))
        self.assertFalse(avail.is_any(None))

    def test_no_read_at_all_says_so_and_keeps_the_designs_norm(self):
        # blind, a build is what it always was (fast inserter, medium pole) rather than the slow
        # tier: a rate report or a lab has no snapshot and must not be quietly downgraded
        got, note = avail.choose("hand", "any")
        self.assertEqual(got, "fast-inserter")
        self.assertIn("no stock read yet", note)
        self.assertEqual(avail.choose("pole", "any")[0], "medium-electric-pole")

    def test_an_unknown_family_is_a_bug_not_a_choice(self):
        with self.assertRaises(ValueError):
            avail.choose("belt", "any")

    def test_every_choice_is_reported_once(self):
        avail.install(sup(KIT["inserter"], KIT["fast"]))
        avail.choose("hand", "any")
        avail.choose("hand", "any")
        avail.choose("pole", "any")
        self.assertEqual(len(avail.drain()), 2)
        self.assertEqual(avail.drain(), [])


class SnapshotTest(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        d = tmp()
        self.addCleanup(gone, d)
        supply_rows = sup(KIT["inserter"], KIT["medium"])
        path = avail.save(d, supply_rows, "test")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            self.assertIn("when", json.load(fh))
        got = avail.load(d)
        self.assertEqual(got.tick, 1)
        self.assertEqual(got.when, "test")
        self.assertIn("inserter", got.sup.entities)
        self.assertTrue(avail.choose("hand", "any", need=1)[0] in avail.HANDS)   # save() installed it
        empty = avail.load(gone_and_empty := os.path.join(d, "nope"))
        self.assertIsNone(empty.sup)
        self.assertFalse(os.path.exists(gone_and_empty))


class DesignTest(unittest.TestCase):
    """``inserter=any`` on a row, resolved where the entities are named (``fkcore.expand``)."""

    def setUp(self):
        self.dir = tmp()
        self.addCleanup(gone, self.dir)
        avail._snapshot = avail.Snapshot()
        avail._notes = []

    def tearDown(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    def lay(self, src, *rows):
        avail.install(sup(*rows))
        f = parse(src, "t.fk")
        flat = elaborate(f, dict(f.modules), CAT, "t")
        lay, _notes = expand.expand_factory(flat, CAT)
        return lay

    def names(self, lay):
        return sorted(e.name for k, e in lay.entities.items()
                      if k.startswith("gears/") and CAT.kind(e.name) == "inserter")

    def test_any_lays_the_lowest_rung_and_the_hands_step_raises_it(self):
        # the row comes in plain; `fkcore.hands` (not expand) is what gives a gear row fast hands,
        # because that is a question about the flow and the connector, not about the prototype
        src = ("plates = Chest<requester, item=iron-plate, rate=1/s> @(0, 5)\n"
               "gears = AsmRow<n=2, recipe=iron-gear-wheel, inserter=any> @(2, 0)\n"
               "box = Chest<provider> @(2, 12)\n"
               "net plates: plates -> gears\nnet gear: gears -> box\n")
        self.assertEqual(set(self.names(self.lay(src, *KIT.values()))), {"inserter"})
        self.assertEqual(set(self.names(self.lay(src, *KIT.values()))), {"inserter"})

    def test_best_takes_the_fast_hand_where_it_can_be_built(self):
        src = ("plates = Chest<requester, item=iron-plate, rate=1/s> @(0, 5)\n"
               "gears = AsmRow<n=2, recipe=iron-gear-wheel, inserter=best> @(2, 0)\n"
               "box = Chest<provider> @(2, 12)\n"
               "net plates: plates -> gears\nnet gear: gears -> box\n")
        lay = self.lay(src, KIT["inserter"], row("fast-inserter", 90))
        self.assertEqual(set(self.names(lay)), {"fast-inserter"})
        self.assertTrue(avail.drain())        # the build says which one it took

    def test_a_row_without_inserter_takes_the_lowest_rung_too(self):
        src = ("plates = Chest<requester, item=iron-plate, rate=1/s> @(0, 5)\n"
               "gears = AsmRow<n=2, recipe=iron-gear-wheel> @(2, 0)\n"
               "box = Chest<provider> @(2, 12)\n"
               "net plates: plates -> gears\nnet gear: gears -> box\n")
        self.assertEqual(set(self.names(self.lay(src, *KIT.values()))), {"inserter"})

    def test_a_name_is_still_a_name(self):
        src = ("plates = Chest<requester, item=iron-plate, rate=1/s> @(0, 5)\n"
               "gears = AsmRow<n=2, recipe=iron-gear-wheel, inserter=inserter> @(2, 0)\n"
               "box = Chest<provider> @(2, 12)\n"
               "net plates: plates -> gears\nnet gear: gears -> box\n")
        self.assertEqual(set(self.names(self.lay(src, *KIT.values()))), {"inserter"})

    def test_a_typo_says_what_an_inserter_is(self):
        # a row's inserter= is checked where the row is named; a factory expansion reports a
        # malformed fragment as an UNPLACED line, as it does for every other fragment error
        def flat_of(src):
            avail.install(sup(*KIT.values()))
            f = parse(src, "t.fk")
            return elaborate(f, dict(f.modules), CAT, "t")

        src = ("plates = Chest<requester, item=iron-plate, rate=1/s> @(0, 5)\n"
               "gears = AsmRow<n=2, recipe=iron-gear-wheel, inserter=fastinsert> @(2, 0)\n"
               "net plates: plates -> gears\n")
        flat = flat_of(src)
        with self.assertRaises(FragmentError) as got:
            expand.fragment_of(flat, "gears", CAT)
        self.assertIn("no prototype 'fastinsert'", str(got.exception))
        flat.insts["gears"].params["inserter"] = "transport-belt"
        with self.assertRaises(FragmentError) as got:
            expand.fragment_of(flat, "gears", CAT)
        self.assertIn("is a transport-belt, not an inserter", str(got.exception))
        _lay, notes = expand.expand_factory(flat, CAT)
        self.assertTrue(any("not an inserter" in n for n in notes), notes)


class ScriptTest(unittest.TestCase):
    """A build script says ``--hand any`` and ``--pole any``: the steps line up with the snapshot."""

    def setUp(self):
        self.dir = tmp()
        self.addCleanup(gone, self.dir)
        for name, text in (("shop.fk", SHOP_FK), ("mall.surface", SHOP_SURFACE),
                           ("mall.build.fkb", SHOP_SCRIPT)):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        avail._snapshot, avail._notes = avail.Snapshot(), []
        self.script = os.path.join(self.dir, "mall.build.fkb")

    def tearDown(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    def run_build(self, rows):
        avail.save(self.dir, sup(*rows), "test")
        code, ctx = flow.run(self.script, None, None, CAT, echo=lambda _l: None)
        self.assertEqual(code, 0)
        with open(os.path.join(self.dir, "out", "route.txt"), encoding="utf-8") as fh:
            route_txt = fh.read()
        with open(os.path.join(self.dir, "out", "cover_power.txt"), encoding="utf-8") as fh:
            cover_txt = fh.read()
        return ctx, route_txt, cover_txt

    def test_the_router_and_the_poles_take_what_the_network_has(self):
        ctx, route_txt, cover_txt = self.run_build(list(KIT.values()))
        lay = ctx.layouts["gear"]
        hands = {e.name for e in lay.entities.values()
                 if e.owner.startswith("~") and CAT.kind(e.name) == "inserter"}
        self.assertNotIn("fast-inserter", hands)                 # not researched: not laid
        self.assertEqual(hands - {"long-handed-inserter"}, {"inserter"})   # 2 tiles reach: long
        self.assertIn("hand=any: inserter", route_txt)
        poles = {e.name for e in lay.entities.values() if CAT.kind(e.name) == "electric-pole"}
        self.assertEqual(poles, {"medium-electric-pole"})         # in the kit
        self.assertIn("pole=any: medium-electric-pole", cover_txt)

    def test_small_poles_once_the_medium_ones_are_not_buildable(self):
        rows = [row("inserter", 50), row("fast-inserter", 40),
                row("medium-electric-pole", 0, enabled=False), row("small-electric-pole", 60)]
        ctx, _route_txt, cover_txt = self.run_build(rows)
        lay = ctx.layouts["gear"]
        poles = {e.name for e in lay.entities.values() if CAT.kind(e.name) == "electric-pole"}
        self.assertEqual(poles, {"small-electric-pole"})
        self.assertIn("pole=any: small-electric-pole", cover_txt)

    def test_a_standing_route_gives_up_the_hand_nobody_can_build(self):
        # 2.0.14: a route that stands keeps its carriers, so a run that pasted fast inserters while
        # they could be built keeps exactly those. Its own script (--hand fast-inserter) lays them
        # first; the next build takes the lowest rung and gives up the hand robots cannot build,
        # in place and without re-routing the net.
        fast_script = SHOP_SCRIPT.replace("--hand any", "--hand fast-inserter")
        path = os.path.join(self.dir, "fast.build.fkb")
        with open(self.script, encoding="utf-8") as fh:
            default = fh.read()
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(fast_script)
        avail.save(self.dir, sup(row("inserter", 50), row("fast-inserter", 40),
                                 row("medium-electric-pole", 93, enabled=False)), "test")
        code, ctx = flow.run(path, None, None, CAT, echo=lambda _l: None)
        self.assertEqual(code, 0)
        built = {e.name for e in ctx.layouts["gear"].entities.values()
                 if e.owner.startswith("~") and CAT.kind(e.name) == "inserter"}
        self.assertEqual(built - {"long-handed-inserter"}, {"fast-inserter"})   # long: 2 tiles
        with open(self.script, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(default)
        ctx, route_txt, _cover = self.run_build(list(KIT.values()))
        hands = {e.name for e in ctx.layouts["gear"].entities.values()
                 if e.owner.startswith("~") and CAT.kind(e.name) == "inserter"}
        self.assertNotIn("fast-inserter", hands)
        self.assertIn("2 kept (2 pinned from the committed .fkp)", route_txt)   # it stands
        self.assertIn("rehanded  2 standing inserters robots cannot build, to inserter", route_txt)

    def test_a_pole_typo_is_an_error_line_not_a_traceback(self):
        path = os.path.join(self.dir, "mall.build.fkb")
        with open(self.script, encoding="utf-8") as fh:
            text = fh.read().replace("--pole any", "--pole mediun-electric-pole")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        avail.save(self.dir, sup(*KIT.values()), "test")
        with self.assertRaises(flow.FlowError) as got:
            flow.run(self.script, None, None, CAT, echo=lambda _l: None)
        self.assertIn("not an electric pole", str(got.exception))


class AgentWrapperTest(unittest.TestCase):
    """``agent/fk.py`` reads the snapshot on the host before a design half that has none."""

    def test_the_wrapper_prefetches_the_avail_read(self):
        path = os.path.join(os.path.dirname(__file__), "..", "agent", "fk.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"avail"', src)                     # a host command (it reads the game)
        self.assertIn("_avail_first(cfg)", src)
        self.assertIn('"avail", ".", "--save"', src)


if __name__ == "__main__":
    unittest.main()
