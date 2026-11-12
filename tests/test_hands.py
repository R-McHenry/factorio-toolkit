"""fkcore.hands (2.0.15): every short hand is the lowest rung, raised only where the flow needs one.

Rory, 2026-10-25: "The default should probably be lowest, and it would go higher if it senses a
bottleneck in thruput model at the inserter."

The model answers the question: ``fkcore.routed.required`` is the flow through every connector with
the machines at nominal rates and **no capacities**, so it does not depend on the hand that is laid,
and ``fkcore.lanes.inserter_rate`` gives each rung's rate (hand size, bulk, drop onto a belt). A
stone furnace takes 0.33/s all in: a plain inserter (0.86/s) is enough, and it stays plain. A gear
assembler takes 2 plates/s: no plain hand carries that, so those hands are raised.
"""
import os
import tempfile
import unittest

from fkcore import avail, flow, hands, supply
from fkcore.catalog import Catalog
from fkcore.connect import REACH

CAT = Catalog.load()

SURFACE = """\
surface  small
mode     lab
terrain  none
catalog  base
place gear = main plot 0,0 40x30
"""
SCRIPT = """\
read_surface    small
read_terrain    none
elaborate
place           --keep pinned
route           --only stale --effort normal --hand any
hands {mode}
report_checks
write_layout
"""
#: each gear assembler: 2 plates in, 1 gear out a second. No plain hand carries 2/s.
GEARS = """\
plates = Chest<requester, item=iron-plate, rate=4/s> @(0, 4)
gears  = AsmRow<n=2, recipe=iron-gear-wheel{extra}>      @(4, 0)
box    = Chest<provider>                            @(0, 12)
net plates_: plates -> gears
net gear_:   gears -> box
"""
#: each stone furnace: 0.31 plates out, 0.31 ore and 0.02 coal in. A plain hand is enough.
SMELT = """\
iore   = Chest<requester, item=iron-ore, rate=0.6/s> @(0, 4)
icoal  = Chest<requester, item=coal, rate=0.1/s>    @(0, 10)
smelt  = SmelterRow<n=2, recipe=iron-plate{extra}>   @(4, 0)
ibox   = Chest<provider>                            @(0, 16)
net iore_:   iore -> smelt
net ifuel:   icoal -> smelt
net iplates: smelt -> ibox
"""

_TMP = [0]


def tmp(prefix="fkhands-"):
    """A scratch dir made here: ``tempfile.mkdtemp()`` dirs are unwritable under the DSH file
    sandbox (the workspace's STATE.md says so)."""
    _TMP[0] += 1
    path = os.path.join(tempfile.gettempdir(), f"{prefix}{os.getpid()}-{_TMP[0]}")
    os.makedirs(path, exist_ok=True)
    return path


def gone(path):
    __import__("shutil").rmtree(path, ignore_errors=True)


def row(name, stock=0, enabled=True):
    return {"entity": name, "item": name, "stock": stock, "known": True, "enabled": enabled}


def supply_of(*rows):
    return supply.from_raw({"tick": 1, "force": "player", "surface": "nauvis", "networks": 1,
                            "entities": list(rows), "recipes": [], "research": {}})


def hands_in(lay, cat=CAT):
    """The short hands of a layout (reach 1: a long-handed inserter is the router's geometry)."""
    return {e.name for e in lay.entities.values()
            if cat.has_entity(e.name) and cat.kind(e.name) == "inserter"
            and REACH.get(e.name, 1) == 1}


class RungTest(unittest.TestCase):
    def test_the_lowest_rung_that_carries_the_flow(self):
        self.assertEqual(hands.choose(0.3, False)[0], "inserter")
        self.assertEqual(hands.choose(0.85, False)[0], "inserter")
        self.assertEqual(hands.choose(2.0, False)[0], "fast-inserter")
        name, rate = hands.choose(9.0, False)        # nothing carries it: the top rung says so
        self.assertEqual(name, "fast-inserter")
        self.assertAlmostEqual(rate, 2.5)

    def test_onto_a_belt_loses_nothing_at_hand_one(self):
        # the derating starts at hand 3 (lanes._ONTO_BELT)
        self.assertAlmostEqual(hands.choose(0.5, True, hand=1)[1],
                               hands.choose(0.5, False, hand=1)[1])
        self.assertLess(hands._rate("fast-inserter", 3, 1, True, CAT),
                        hands._rate("fast-inserter", 3, 1, False, CAT))


class Codebase:
    """One game codebase in a scratch dir, built through the real script."""

    def __init__(self, test, fk, rows=(), mode="minimize"):
        self.dir = tmp()
        test.addCleanup(gone, self.dir)
        self.write("main.fk", fk)
        self.write("small.surface", SURFACE)
        self.write("small.build.fkb", SCRIPT.format(mode=mode))
        self.snapshot(*rows)

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def snapshot(self, *rows):
        avail.save(self.dir, supply_of(*rows), "test")

    def run(self, mode=None, to=None):
        if mode is not None:
            self.write("small.build.fkb", SCRIPT.format(mode=mode))
        return flow.run(os.path.join(self.dir, "small.build.fkb"), None, to, CAT,
                        echo=lambda _l: None)

    def text(self, step):
        with open(os.path.join(self.dir, "out", f"{step}.txt"), encoding="utf-8") as fh:
            return fh.read()


KIT = (row("inserter", 60), row("fast-inserter", 200))


class GearsTest(unittest.TestCase):
    def setUp(self):
        self._saved = (avail._snapshot, avail._notes)
        self.code = Codebase(self, GEARS.format(extra=""), KIT)

    def tearDown(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    def test_a_gear_row_is_raised_to_fast_hands(self):
        code, ctx = self.code.run()
        self.assertEqual(code, 0)
        self.assertIn("fast-inserter", hands_in(ctx.layouts["gear"]))
        txt = self.code.text("hands")
        self.assertIn("hand minimize", txt)
        self.assertIn("raised for the flow", txt)
        self.assertIn("gears/f0", txt)

    def test_the_lowest_rung_is_what_gets_laid_first(self):
        _code, ctx = self.code.run(to="place")
        self.assertEqual(hands_in(ctx.layouts["gear"]), {"inserter"})

    def test_maximize_takes_the_top_rung(self):
        _code, ctx = self.code.run(mode="maximize")
        self.assertEqual(hands_in(ctx.layouts["gear"]), {"fast-inserter"})


class StarvedTest(unittest.TestCase):
    # 3.0 (the live run, ~7820k): B5's cable hand was left plain because the model saw no plastic
    # upstream and ran all of B5 at 0. A shortage upstream never shrinks a hand: the gears here get
    # 0.2 plates/s in the model, and their output hands are still sized for what they make when the
    # plates come (the hands off the requester carry what it is written to give, 0.2/s)
    def setUp(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []
        self.addCleanup(lambda: setattr(avail, "_snapshot", avail.Snapshot()))

    def test_a_starved_row_is_sized_for_its_inputs_arriving(self):
        code = Codebase(self, GEARS.format(extra="").replace("rate=4/s", "rate=0.2/s"), KIT)
        _c, ctx = code.run()
        self.assertIn("fast-inserter", hands_in(ctx.layouts["gear"]))
        self.assertIn("raised for the flow: gears/o0", code.text("hands"))


class SmeltTest(unittest.TestCase):
    def setUp(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []
        self.addCleanup(lambda: setattr(avail, "_snapshot", avail.Snapshot()))

    def test_a_stone_furnace_row_stays_plain(self):
        code = Codebase(self, SMELT.format(extra=""), KIT)
        _c, ctx = code.run()
        self.assertEqual(hands_in(ctx.layouts["gear"]), {"inserter"})
        self.assertIn("0 changed", code.text("hands"))

    def test_a_named_hand_is_left_alone(self):
        code, ctx = Codebase(self, SMELT.format(extra=", inserter=fast-inserter"), KIT).run()
        self.assertEqual(code, 0)
        row_hands = {e.name for e in ctx.layouts["gear"].entities.values()
                     if e.owner == "smelt" and CAT.kind(e.name) == "inserter"
                     and REACH.get(e.name, 1) == 1}
        self.assertEqual(row_hands, {"fast-inserter"})     # the design named it: not touched
        taps = {e.name for e in ctx.layouts["gear"].entities.values()
                if e.owner.startswith("~") and CAT.kind(e.name) == "inserter"
                and REACH.get(e.name, 1) == 1}
        self.assertEqual(taps - {"inserter"}, set())        # its own taps: the lowest rung


class RouteHandTest(unittest.TestCase):
    # FRICTION 11-11 (the bootstrap stages): `route --hand inserter` fixes every tap, and the
    # hands step said "0 short hands" while one plain hand held a whole line
    def setUp(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []
        self.addCleanup(lambda: setattr(avail, "_snapshot", avail.Snapshot()))

    def test_a_hand_route_named_is_left_and_said_too_thin(self):
        code = Codebase(self, GEARS.format(extra=""), KIT)
        code.write("small.build.fkb", SCRIPT.format(mode="minimize")
                   .replace("--hand any", "--hand inserter"))
        rc, ctx = code.run()
        self.assertEqual(rc, 0)
        txt = code.text("hands")
        self.assertIn("left as the design or `route --hand` named them", txt)
        self.assertIn("carry less than their connector needs", txt)
        self.assertIn("`route --hand any` lets this step raise them", txt)
        taps = {e.name for e in ctx.layouts["gear"].entities.values()
                if e.owner.startswith("~") and CAT.kind(e.name) == "inserter"}
        self.assertEqual(taps - {"inserter", "long-handed-inserter"}, set())   # not raised


class UnbuildableTest(unittest.TestCase):
    def setUp(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    def test_a_rung_the_network_cannot_build_is_skipped_and_says_so(self):
        rows = (row("inserter", 60), row("fast-inserter", 0, enabled=False))
        code = Codebase(self, GEARS.format(extra=""), rows)
        _c, ctx = code.run()
        self.assertNotIn("fast-inserter", hands_in(ctx.layouts["gear"]))   # a LOCKED ghost
        self.assertIn("fast-inserter is not buildable now", code.text("hands"))


class DowngradeTest(unittest.TestCase):
    def setUp(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    def test_a_standing_fast_hand_stays_unless_downgrade(self):
        code = Codebase(self, SMELT.format(extra=""), KIT, mode="maximize")
        code.run(mode="maximize")                       # fast hands stand, written to the .fkp
        _c, ctx = code.run(mode="minimize")             # the flow does not need them
        self.assertIn("fast-inserter", hands_in(ctx.layouts["gear"]))
        self.assertIn("kept from the committed .fkp", code.text("hands"))
        code.write("small.build.fkb", SCRIPT.format(mode="minimize --downgrade"))
        _c, ctx = code.run()
        self.assertEqual(hands_in(ctx.layouts["gear"]), {"inserter"})


class ArgsTest(unittest.TestCase):
    def setUp(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    def test_a_long_hand_is_not_a_rung(self):
        code = Codebase(self, SMELT.format(extra=""), KIT)
        code.write("small.build.fkb",
                   SCRIPT.format(mode="minimize --allow inserter,long-handed-inserter"))
        with self.assertRaises(flow.FlowError) as got:
            code.run()
        self.assertIn("not a short hand", str(got.exception))

    def test_a_bad_mode_is_a_script_error(self):
        code = Codebase(self, SMELT.format(extra=""), KIT)
        code.write("small.build.fkb", SCRIPT.format(mode="faster"))
        with self.assertRaises(flow.FlowError):
            code.run()


class LiteralTest(unittest.TestCase):
    """A Literal is pinned as it is (``fkcore.tiers`` says so too): its hands are not the step's."""

    def setUp(self):
        avail._snapshot, avail._notes = avail.Snapshot(), []

    def test_a_literal_keeps_its_own_hand(self):
        fk = (SMELT.format(extra="")
              + 'part = Literal<file="part.json"> @(20, 20)\n')
        code = Codebase(self, fk, KIT)
        code.write("part.json", '[{"name": "fast-inserter", "x": 20.5, "y": 20.5}]')
        rc, ctx = code.run()
        self.assertEqual(rc, 0)
        self.assertIn("fast-inserter", hands_in(ctx.layouts["gear"]))   # the Literal's own
        self.assertIn("0 changed", code.text("hands"))


if __name__ == "__main__":
    unittest.main()
