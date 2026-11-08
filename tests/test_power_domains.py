"""2.1, power domains and switching (PLAN-2.1 "Power domains and switching", Rory 2026-10-31):
domains covered apart, copper lines, PowerSwitch, Accumulator<read=>, Decider and Arithmetic with
their .in and .out sides, the checks no-source, power-short, switch-never and domain-overlap, and
power by domain in the run stats."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import circuits, codec, cover, domains, fkp, flow, lang, runstats, settings
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate

CAT = Catalog.load()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = ("read_surface nauvis\nread_terrain none\nelaborate\nreport_rates\nplace --keep pinned\n"
          "route --only stale\ncover power --pole medium-electric-pole\nfloorplan\nreport_checks\n"
          "write_layout\n")

PAIR = """
power a: cover all
power b: cover b1, b2
a1 = Assembler<recipe=iron-gear-wheel> @(0, 1)
a2 = Assembler<recipe=iron-gear-wheel> @(0, 6)
b1 = Assembler<recipe=iron-gear-wheel> @(10, 1)
b2 = Assembler<recipe=iron-gear-wheel> @(10, 6)
"""

SHED = """
signal A = signal-A
signal S = signal-S
power main: cover all
power shed: cover r1, r2
acc   = Accumulator<read=A> @(2, 2)
acc2  = Accumulator @(2, 5)
latch = Decider<if="green.A < 20 or (red.S > 0 and green.A < 80)", out="S=1"> @(6, 2)
wire level green: acc -> latch.in
wire hold  red:   latch.out -> latch.in
sw = PowerSwitch @(10, 2) when hold.S = 0
copper feed: main -> sw.left
copper load: sw.right -> shed
r1 = Entity<name=radar> @(20, 1)
r2 = Entity<name=radar> @(20, 5)
"""


def flat_of(src):
    f = lang.parse(src, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


class Build:
    """A paper build of a .fk in a temp dir: the layout, the report lines and the check lines."""

    def __init__(self, src, size="40x16", files=None):
        self.dir = tempfile.mkdtemp(prefix="fkdomains-")
        for name, text in dict(files or {}, **{"t.fk": src, "nauvis.build.fkb": SCRIPT,
                                               "nauvis.surface": "surface nauvis\n"
                                               f"terrain none\nplace t = t plot 0,0 {size}\n"}).items():
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        self.code, self.ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                                       echo=lambda _l: None)
        path = os.path.join(self.dir, "t.fkp")
        self.lay = fkp.load(path) if os.path.exists(path) else None
        self.checks = [(c.code, c.where, c.msg) for _step, c in self.ctx.checks]
        with open(os.path.join(self.dir, "out", "cover_power.txt"), encoding="utf-8") as fh:
            self.cover = fh.read()

    def codes(self, code):
        return [c for c in self.checks if c[0] == code]

    def poles(self):
        return {k: e for k, e in self.lay.entities.items() if e.name == "medium-electric-pole"}

    def close(self):
        shutil.rmtree(self.dir, True)


def build(test, src, **kw):
    b = Build(src, **kw)
    test.addCleanup(b.close)
    test.assertEqual(b.code, 0, b.ctx.log if hasattr(b.ctx, "log") else "")
    return b


class LanguageTest(unittest.TestCase):
    def test_copper_parses(self):
        f = lang.parse("power a: cover all\npower b: cover x\ncopper j: a -> sw.left\n", "t.fk")
        c = f.body.coppers[0]
        self.assertEqual((c.name, c.a.parts, c.b.parts), ("j", ["a"], ["sw", "left"]))

    def test_copper_in_a_module_is_refused(self):
        with self.assertRaisesRegex(ElabError, "top level"):
            flat_of("module M {\n  copper j: a -> b\n}\nm = M @(0, 0)\n")

    def test_the_prelude_has_powerswitch_and_accumulator(self):
        flat = flat_of("sw = PowerSwitch @(0, 0)\nacc = Accumulator<read=signal-A> @(3, 0)\n")
        self.assertEqual(flat.machines["sw/m0"].prototype, "power-switch")
        self.assertEqual(flat.machines["acc/m0"].prototype, "accumulator")
        self.assertEqual(flat.circuit.emits["acc/m0"], {"signal-A"})

    def test_read_on_another_entity_is_refused(self):
        with self.assertRaisesRegex(ElabError, "accumulator"):
            flat_of("r = Entity<name=radar, read=signal-A> @(0, 0)\n")

    def test_the_two_preludes_are_one(self):
        with open(os.path.join(ROOT, "fkcore", "prelude.fk"), encoding="utf-8") as a, \
                open(os.path.join(ROOT, "kickoff", "template", "game", "prelude.fk"),
                     encoding="utf-8") as b:
            self.assertEqual(a.read(), b.read())


class CombinatorTest(unittest.TestCase):
    def test_a_condition_is_or_between_groups_of_and(self):
        self.assertEqual(circuits.parse_decider("green.A < 20 or (red.S > 0 and green.A < 80)"),
                         [[("green.A", "<", 20)], [("red.S", ">", 0), ("green.A", "<", 80)]])
        self.assertEqual(circuits.parse_decider("A >= B and iron-plate != 3"),
                         [[("A", ">=", "B"), ("iron-plate", "!=", 3)]])
        self.assertEqual(circuits.parse_decider("A == -5"), [[("A", "=", -5)]])

    def test_bad_conditions_are_refused(self):
        for text in ("(A < 1 or B < 2) and C < 3", "A < 1 and", "A <", "A < 1 B < 2", "",
                     "(A < 1", "A < 1)", "or A < 1"):
            with self.assertRaises(ValueError, msg=text):
                circuits.parse_decider(text)

    def test_outputs_and_calc(self):
        self.assertEqual(circuits.parse_outputs("S=1, T"), [("S", 1), ("T", None)])
        self.assertEqual(circuits.parse_calc("red.A * 2"), ("red.A", "*", 2))
        self.assertEqual(circuits.parse_calc("each AND 255"), ("each", "AND", 255))
        for text in ("A*2", "A ** 2", "A * 2 * 3"):
            with self.assertRaises(ValueError, msg=text):
                circuits.parse_calc(text)

    def test_a_decider_takes_the_games_form(self):
        # as the game exports it (a laptop server, 2.0.77, 2026-10-31): the comparator "<", the
        # constant 0, compare_type "or", a constant output of 1 and both networks left out
        b = build(self, SHED)
        cb = json.loads(b.lay.entities["latch/m0"].attrs["cb"])
        sig = lambda n: {"type": "virtual", "name": n}
        self.assertEqual(cb, {"decider_conditions": {
            "conditions": [
                {"first_signal": sig("signal-A"), "constant": 20,
                 "first_signal_networks": {"red": False, "green": True}},
                {"first_signal": sig("signal-S"), "comparator": ">",
                 "first_signal_networks": {"red": True, "green": False}},
                {"first_signal": sig("signal-A"), "constant": 80,
                 "first_signal_networks": {"red": False, "green": True}, "compare_type": "and"}],
            "outputs": [{"signal": sig("signal-S"), "copy_count_from_input": False}]}})
        self.assertEqual(json.loads(b.lay.entities["acc/m0"].attrs["cb"]),
                         {"output_signal": sig("signal-A")})

    def test_an_arithmetic_combinator(self):
        flat = flat_of('signal B = signal-B\nx = Arithmetic<calc="green.signal-A * 2", out="B"> '
                       '@(0, 0)\n')
        props = [p for p, _s in flat.circuit.sets if p.target == "x"]
        got = props[0].attrs["cb.arithmetic_conditions"].value
        self.assertEqual(got, {"first_signal": "signal-A", "second_constant": 2, "operation": "*",
                               "output_signal": "signal-B",
                               "first_signal_networks": {"red": False, "green": True}})
        self.assertEqual(flat.circuit.emits["x/m0"], {"signal-B"})

    def test_a_bad_condition_is_a_circuit_line(self):
        flat = flat_of('x = Decider<if="(A < 1 or B < 2) and C < 3", out="S=1"> @(0, 0)\n')
        self.assertTrue(any(c.code == "CIRCUIT" and "or between groups" in c.msg
                            for c in flat.checks))

    def test_the_sides_and_the_latch_wire(self):
        b = build(self, SHED)
        ws = {(w.net, w.colour, w.a, w.b) for w in b.lay.wires}
        self.assertIn(("hold", "red", "latch/m0.in", "latch/m0.out"), ws)
        self.assertIn(("hold", "red", "latch/m0.out", "sw/m0"), ws)
        self.assertIn(("level", "green", "acc/m0", "latch/m0.in"), ws)
        self.assertIn(("feed", "copper", "power/p0", "sw/m0.left"), ws)
        self.assertIn(("load", "copper", "power-shed/p0", "sw/m0.right"), ws)
        self.assertFalse(b.codes("wires-share"))
        # the blueprint's wires, as the game numbers them (measured: [acc 2, latch 2], [latch 1,
        # latch 3], [latch 3, switch 1], [pole 5, switch 5], [pole 5, switch 6])
        rows = codec.rows_of(b.lay)
        num = {r["src"]: i + 1 for i, r in enumerate(rows)}
        got = {tuple(w) for w in codec.wire_list(rows, codec.pole_wires(rows, CAT),
                                                 codec.links_of(rows, b.lay.wires))}
        self.assertTrue({(num["acc/m0"], 2, num["latch/m0"], 2),
                         (num["latch/m0"], 1, num["latch/m0"], 3),
                         (num["latch/m0"], 3, num["sw/m0"], 1),
                         (num["power-shed/p0"], 5, num["sw/m0"], 6),
                         (num["power/p0"], 5, num["sw/m0"], 5)} <= got)
        poles = {num[k] for k in b.poles()}
        self.assertFalse([w for w in got if w[0] in poles and w[2] in poles], "no pole-to-pole "
                         "copper between the two domains")
        # and the .fkp and the blueprint keep them
        self.assertEqual(fkp.dumps(fkp.loads(fkp.dumps(b.lay))), fkp.dumps(b.lay))
        back = codec.blueprint_to_fkp(codec.fkp_to_blueprint(b.lay, CAT))
        self.assertEqual(fkp.dumps(back), fkp.dumps(b.lay))

    def test_the_switch_takes_when(self):
        b = build(self, SHED)
        self.assertEqual(b.lay.entities["sw/m0"].attrs["if"], "signal-S=0")

    def test_a_side_on_the_wrong_role_is_a_no_wire_line(self):
        flat = flat_of('x = Decider<if="signal-A > 0", out="signal-B=1"> @(0, 0)\n'
                       'c = Constant<signals="signal-A=1"> @(3, 0)\n'
                       'wire w red: x.in -> c\n')
        self.assertTrue(any(c.code == "no-wire" and "x.out" in c.msg for c in flat.checks))

    def test_a_latch_wire_is_no_drift(self):
        rows = [{"n": 1, "name": "decider-combinator", "x": 0.5, "y": 1,
                 "e": {"name": "decider-combinator", "wires": [[1, 1, 1, 3]]}}]
        got = settings.live({"rows": rows})
        self.assertEqual(got[("decider-combinator", 0.5, 1.0)][1],
                         {(1, ("decider-combinator", 0.5, 1.0), 3),
                          (3, ("decider-combinator", 0.5, 1.0), 1)})


class DomainTest(unittest.TestCase):
    def test_one_power_line_is_as_before(self):
        b = build(self, "power grid: cover all\na1 = Assembler<recipe=iron-gear-wheel> @(0, 1)\n"
                        "b1 = Assembler<recipe=iron-gear-wheel> @(10, 1)\n")
        self.assertIsNone(domains.active(b.ctx.flats["t"]))
        self.assertTrue(all(k.startswith("power/") and "domain" not in e.attrs
                            for k, e in b.poles().items()))
        self.assertNotIn("domain", b.cover)
        self.assertFalse(os.path.exists(os.path.join(b.dir, "out", "power-domains.json")))

    def test_two_domains_are_covered_apart(self):
        b = build(self, PAIR)
        poles = b.poles()
        self.assertEqual(sorted(poles), ["power-b/p0", "power/p0"])
        self.assertEqual(poles["power-b/p0"].attrs.get("domain"), "b")
        self.assertNotIn("domain", poles["power/p0"].attrs)
        self.assertIn("cover power-b power pole=medium-electric-pole", fkp.dumps(b.lay))
        # in each other's reach, and still not wired: two networks
        rows = codec.rows_of(b.lay)
        self.assertEqual(codec.pole_wires(rows, CAT), [])
        self.assertEqual(len(cover.networks(list(b.lay.entities.values()), CAT)), 2)
        # no pole reaches the other domain's machines
        for k, e in poles.items():
            mine = "b" if k.startswith("power-b") else "a"
            for m in ("a1", "a2", "b1", "b2"):
                if m[0] == mine:
                    continue
                me = b.lay.entities[f"{m}/m0"]
                self.assertFalse(cover._overlap(cover._rect(fkp.tiles_of(CAT, me)), float(e.x),
                                                float(e.y), CAT.pole_supply(e.name)), (k, m))
        with open(os.path.join(b.dir, "out", "power-domains.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"domains": {"a": [[3.5, 3.5]], "b": [[7.5, 3.5]]}})

    def test_two_plots_domains_of_one_name_stay_apart(self):
        rows = [{"src": "n:one/power-b/p0", "name": "medium-electric-pole", "x": 0.5, "y": 0.5,
                 "attrs": {"domain": "b"}},
                {"src": "n:two/power-b/p0", "name": "medium-electric-pole", "x": 4.5, "y": 0.5,
                 "attrs": {"domain": "b"}},
                {"src": "n:one/power/p0", "name": "medium-electric-pole", "x": 2.5, "y": 0.5,
                 "attrs": {}},
                {"src": "n:two/power/p0", "name": "medium-electric-pole", "x": 6.5, "y": 0.5,
                 "attrs": {}}]
        self.assertEqual(codec.pole_wires(rows, CAT), [(2, 3)])

    def test_domain_overlap_where_every_spot_reaches_the_other(self):
        b = build(self, "power a: cover all\npower b: cover b1\n"
                        "a1 = Assembler<recipe=iron-gear-wheel> @(0, 0)\n"
                        "b1 = Assembler<recipe=iron-gear-wheel> @(4, 0)\n", size="8x8")
        got = b.codes("domain-overlap")
        self.assertTrue(got and "another power domain" in got[0][2], b.checks)
        self.assertFalse(b.poles())

    def test_a_copper_line_to_a_switch_far_off_gets_a_bridge_pole(self):
        b = build(self, SHED.replace("sw = PowerSwitch @(10, 2)", "sw = PowerSwitch @(13, 9)"),
                  size="40x16")
        self.assertRegex(b.cover, r"copper (feed|load): .* bridge pole")
        ws = [w for w in b.lay.wires if w.colour == "copper"]
        self.assertEqual(sorted(w.net for w in ws), ["feed", "load"])
        new = [k for k, e in b.poles().items() if k.endswith("/p1")]
        self.assertTrue(new)
        for k in new:
            owner = k.rsplit("/", 1)[0]
            self.assertEqual(b.poles()[k].attrs.get("domain"),
                             None if owner == "power" else owner[len("power-"):])
        self.assertFalse(b.codes("copper"))

    def test_two_domains_joined_with_no_switch_are_one_and_it_says_so(self):
        b = build(self, PAIR + "copper j: a -> b\n")
        self.assertIn("power a and power b are one network now", b.cover)
        self.assertEqual([(w.net, w.colour) for w in b.lay.wires], [("j", "copper")])
        self.assertFalse(b.codes("no-source"))

    def test_no_source(self):
        b = build(self, PAIR)
        self.assertEqual([c[1] for c in b.codes("no-source")], ["t power b"])
        b2 = build(self, SHED)
        self.assertFalse(b2.codes("no-source"))
        self.assertFalse(b2.codes("power-short"))
        self.assertFalse(b2.codes("switch-never"))

    def test_power_short_with_the_switches_open(self):
        src = """
power gen: cover all
power load: cover l
e  = SteamEngine @(0, 0)
r1 = Entity<name=radar> @(6, 0)
r2 = Entity<name=radar> @(6, 4)
sw = PowerSwitch @(12, 2)
copper f: gen -> sw.left
copper g: sw.right -> load
l = Entity<name=radar> @(18, 0)
"""
        b = build(self, src, size="30x12")
        self.assertFalse(b.codes("power-short"), b.checks)      # 600 kW of 900
        b2 = build(self, src + "r3 = Entity<name=radar> @(6, 8)\nr4 = Entity<name=radar> "
                                "@(10, 8)\n", size="30x14")
        got = b2.codes("power-short")
        self.assertEqual(len(got), 1, b2.checks)
        self.assertIn("1.20 MW", got[0][2])
        self.assertIn("900 kW", got[0][2])

    def test_switch_never(self):
        const = ('c = Constant<signals="signal-S=1"> @(0, 0)\nwire w red: c -> sw\n'
                 'sw = PowerSwitch @(3, 0) when w.signal-S = 0\n')
        flat = flat_of(const)
        self.assertEqual([c.where for c in flat.checks if c.code == "switch-never"], ["sw"])
        # a latch that reads only itself never moves either
        alone = ('x = Decider<if="red.signal-S > 0", out="signal-S=1"> @(0, 0)\n'
                 'wire w red: x.out -> x.in\nsw = PowerSwitch @(3, 0) when w.signal-S = 0\n')
        self.assertTrue(any(c.code == "switch-never" for c in flat_of(alone).checks))
        # one that reads the accumulator moves
        self.assertFalse(any(c.code == "switch-never" for c in flat_of(SHED).checks))
        # a signal no driver puts on the wire
        other = const.replace("when w.signal-S", "when w.signal-T")
        self.assertTrue(any(c.code == "switch-never" and "signal-T" in c.msg
                            for c in flat_of(other).checks))

    def test_hysteresis_is_named_from_outside(self):
        src = """
signal A = signal-A
signal S = signal-S
power main: cover all
power labs: cover l1
module Hysteresis<in, out, lo, hi> {
  latch = Decider<if="green.$in < $lo or (red.$out > 0 and green.$in < $hi)", out="$out=1"> @(0, 0)
  wire hold red: latch.out -> latch.in
}
acc = Accumulator<read=A> @(2, 2)
shedder = Hysteresis<in=A, out=S, lo=20, hi=80> @(6, 2)
wire level green: acc -> shedder.latch.in
sw = PowerSwitch @(10, 2) when shedder.hold.S = 0
copper feed: main -> sw.left
copper load: sw.right -> labs
l1 = Lab @(20, 2)
"""
        b = build(self, src)
        ws = {(w.net, w.a, w.b) for w in b.lay.wires}
        self.assertIn(("level", "acc/m0", "shedder/latch/m0.in"), ws)
        self.assertIn(("shedder/hold", "shedder/latch/m0.out", "sw/m0"), ws)
        self.assertEqual(b.lay.entities["sw/m0"].attrs["if"], "signal-S=0")
        cb = json.loads(b.lay.entities["shedder/latch/m0"].attrs["cb"])
        self.assertEqual(cb["decider_conditions"]["conditions"][2]["constant"], 80)
        self.assertFalse(b.codes("no-wire") + b.codes("no-signal") + b.codes("switch-never"))

    def test_the_example_builds_clean(self):
        files = {}
        for name in ("plant.fk", "plant-w3.json", "kit.fk", "kit.json"):
            with open(os.path.join(ROOT, "kickoff", "template", "game", name), encoding="utf-8") as fh:
                files[name] = fh.read()
        with open(os.path.join(ROOT, "tests", "nest", "cells.fk"), encoding="utf-8") as fh:
            files["cells.fk"] = fh.read()
        with open(os.path.join(ROOT, "tests", "power", "power-shed.fk"), encoding="utf-8") as fh:
            src = fh.read()
        b = Build(src, size="2000x2000", files=files)
        self.addCleanup(b.close)
        self.assertEqual(b.code, 0)
        self.assertEqual(b.checks, [])
        self.assertIn("domain labs: cover power-labs", b.cover)
        self.assertIn("copper feed: power/p0 to sw/m0.left", b.cover)


class StatsTest(unittest.TestCase):
    def sample(self, tick, nets):
        return runstats.norm({"tick": tick, "seed": 1, "items": {}, "fluids": {}, "power": nets,
                              "research": {}, "machines": {}, "recipes": {}, "types": {}}, "rcon")

    def test_power_by_domain(self):
        d = tempfile.mkdtemp(prefix="fkstats-")
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "out"))
        with open(os.path.join(d, "out", "power-domains.json"), "w", encoding="utf-8") as fh:
            json.dump({"domains": {"main": [[4.5, 2.5]], "labs": [[17.5, 3.5]]}}, fh)
        doms = runstats.load_domains(d)
        self.assertEqual(doms, {(9, 5): "main", (35, 7): "labs"})
        a = self.sample(100, {"1": {"made": {"solar-panel": 10}, "used": {"lab": 0},
                                    "at": [9, 5, 11, 5]},
                              "2": {"made": {}, "used": {"lab": 5}, "at": [35, 7]},
                              "3": {"made": {"steam-engine": 1}, "used": {}, "at": [99, 99]}})
        b = self.sample(200, {"1": {"made": {"solar-panel": 70}, "used": {"lab": 0},
                                    "at": [9, 5, 11, 5]},
                              "2": {"made": {}, "used": {"lab": 45}, "at": [35, 7]},
                              "3": {"made": {"steam-engine": 3}, "used": {}, "at": [99, 99]}})
        rec = dict(runstats.delta(a, b, doms))["power"]
        self.assertEqual(rec["domains"], {"main": {"made": 60, "used": 0},
                                          "labs": {"made": 0, "used": 40},
                                          runstats.REST: {"made": 2, "used": 0}})
        self.assertEqual(rec["made"], {"solar-panel": 60, "steam-engine": 2})
        self.assertNotIn("domains", dict(runstats.delta(a, b))["power"])

    def test_the_recorder_and_the_rcon_read_are_one_text(self):
        with open(os.path.join(ROOT, "scenario", "fk-play", "fk_stats.lua"), encoding="utf-8") as fh:
            self.assertIn(runstats.SAMPLE_LUA.strip().splitlines()[12], fh.read())
        self.assertIn("at[id]", runstats.SAMPLE_LUA)


if __name__ == "__main__":
    unittest.main()
