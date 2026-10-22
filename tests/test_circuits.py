"""2.0, circuits in the source (Rory, 2026-10-21: "circuit wiring in the source, with all circuit
and logic conditions in the .fk code, inserter limits included"; "Recipe-switch smarts ... belong in
circuits in the game"). The language, the checks on paper, the layout pass (limits, guard, gated
nets, wires), the codec and the re-lay of an entity whose settings changed.
"""
import base64
import copy
import json
import unittest
import zlib
from unittest import mock

from fkcore import apply as applymod, circuits, codec, expand, fkp, lang, link, own, route
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate

CAT = Catalog.load()

MALL = """
fein  = Chest<requester, item=iron-plate, rate=2/s>   @(0, 11)
gear  = Assembler<recipe=iron-gear-wheel{gear}>       @(6, 2)
belt  = Assembler<recipe=transport-belt{belt}>        @(13, 2)
ins   = Assembler<recipe=inserter{ins}>               @(20, 10)
pipe  = AsmRow<n=2, recipe=pipe{pipe}>                @(6, 33)
bbox  = Chest<provider>                               @(18, 3)
ibox  = Chest<provider>                               @(25, 11)
pbox  = Chest<provider>                               @(14, 34)
cuin  = Chest<requester, item=copper-plate, rate=1/s> @(0, 26)
cable = Assembler<recipe=copper-cable>                @(6, 25)
circ  = Assembler<recipe=electronic-circuit>          @(13, 18)

net fe:    fein -> gear, circ, belt, ins, pipe
net cu:    cuin -> cable
net gears: gear -> belt, ins
net cab:   cable -> circ
net circs: circ -> ins
net belts: belt -> bbox
net inss:  ins -> ibox
net pipes: pipe -> pbox
"""


def flat_of(src):
    f = lang.parse(src, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def checks(flat, *codes):
    return sorted((c.code, c.where) for c in flat.checks if not codes or c.code in codes)


def mall(gear="", belt="", ins="", pipe=""):
    return MALL.format(gear=gear, belt=belt, ins=ins, pipe=pipe)


def laid(src):
    """(flat, the routed layout with its circuits, report lines, check lines)."""
    flat = flat_of(src)
    lay, _notes = expand.expand_factory(flat, CAT)
    r = route.route_layout(flat, lay, CAT)
    out, lines, cks = circuits.lay(flat, r.layout, CAT)
    return flat, out, lines, cks


def with_attr(lay, attr):
    return {k: e.attrs[attr] for k, e in lay.entities.items() if attr in e.attrs}


def bp_entities(text):
    bp = json.loads(zlib.decompress(base64.b64decode(text[1:])))["blueprint"]
    return bp["entities"], bp.get("wires", [])


class LanguageTest(unittest.TestCase):
    def test_the_circuit_statements_parse(self):
        f = lang.parse("""
signal temp = signal-T
signal low
reactor = Reactor<read=temperature, signal=temp>  @(2, 5)
cells   = Chest<requester, item=uranium-fuel-cell, request=20, max=50> @(0, 6)
lamp    = Assembler<recipe=iron-gear-wheel> @(9, 9) when ctl.signal-A != 0
net fuel: cells -> reactor   when fuel_ctl.temp < 550
wire fuel_ctl red: reactor -> fuel
wire ctl green: reactor
behave saver on fuel_ctl {
    state coasting: T >= 550 and not reactor.burning   # a comment
    require 550 > hx.min_temperature
    cycle full_load: burning 200 s, coasting 450 s, cells 1 per 650 s
}
expect spent.fill < 1 within 289 h at full_load
""", "p.fk")
        b = f.body
        self.assertEqual([(s.name, s.game) for s in b.signals], [("temp", "signal-T"),
                                                                 ("low", None)])
        net, = b.nets
        self.assertEqual((str(net.when), net.when.op, net.when.right), ("fuel_ctl.temp < 550",
                                                                         "<", 550))
        self.assertEqual(str(b.insts[2].when), "ctl.signal-A != 0")
        self.assertEqual([(w.name, w.colour, [str(r) for r in w.drivers],
                           [str(r) for r in w.consumers]) for w in b.wires],
                         [("fuel_ctl", "red", ["reactor"], ["fuel"]), ("ctl", "green",
                                                                       ["reactor"], [])])
        bh, = b.behaves
        self.assertEqual((bh.name, bh.wire), ("saver", "fuel_ctl"))
        self.assertEqual(bh.lines[0][:2], ("state", "coasting: T >= 550 and not reactor.burning"))
        self.assertEqual(bh.lines[2][1], "full_load: burning 200 s, coasting 450 s, cells 1 per "
                                         "650 s")
        self.assertEqual(b.expects[0].text, "spent.fill < 1 within 289 h at full_load")

    def test_a_condition_reads_a_wire_the_network_or_an_instance(self):
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse("net a: x -> y when 5 < 3\n", "t.fk")
        self.assertIn("t.fk:1", str(cm.exception))
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse("net a: x -> y when ctl < 3\n", "t.fk")
        self.assertIn("W.SIGNAL, network.ITEM or INSTANCE.SIGNAL", str(cm.exception))


class LimitTest(unittest.TestCase):
    """The 2005 and 2039 players set their mall's limits by Lua after every rebuild
    (malllimits.lua); STRATEGY.md: "The per-item limits sit at the makers"."""

    def test_keep_puts_a_logistic_condition_on_the_makers_hop_into_its_chest(self):
        _flat, lay, lines, cks = laid(mall(belt=", keep=200"))
        self.assertEqual(with_attr(lay, "logistic"), {"~belts/i0": "transport-belt<200"})
        self.assertEqual(lay.wires, [])                    # the network counts: no wire
        self.assertIn("belt keep=200: 1 inserter runs while the logistic network holds fewer "
                      "than 200 (~belts/i0)", lines)
        self.assertEqual(cks, [])

    def test_keep_on_a_row_limits_its_output_inserters_onto_the_belt_to_the_chest(self):
        _flat, lay, _lines, _cks = laid(mall(pipe=", keep=100"))
        self.assertEqual(with_attr(lay, "logistic"), {"pipe/o0": "pipe<100", "pipe/o1": "pipe<100"})

    def test_fill_counts_in_the_chest_by_a_red_wire(self):
        _flat, lay, lines, cks = laid(mall(ins=", fill=50"))
        self.assertEqual(with_attr(lay, "if"), {"~inss/i0": "inserter<50"})
        self.assertEqual(lay.wirenets, {"ibox.signals": fkp.WireNet("ibox.signals", "red")})
        self.assertEqual(lay.wires, [fkp.Wire("ibox.signals", "red", "ibox/c0", "~inss/i0")])
        self.assertEqual(cks, [])

    def test_a_limit_with_no_chest_to_limit_says_so(self):
        _flat, lay, _lines, cks = laid(mall(gear=", keep=10"))
        self.assertEqual(with_attr(lay, "logistic"), {})   # gears go to machines only
        self.assertEqual([c.code for c in cks], ["LIMIT"])
        self.assertIn("no inserter takes its product into a chest", cks[0].msg)

    def test_a_changed_limit_changes_the_layout_and_a_removed_one_goes(self):
        flat = flat_of(mall(belt=", keep=200"))
        lay, _n = expand.expand_factory(flat, CAT)
        routed = route.route_layout(flat, lay, CAT).layout
        first, _l, _c = circuits.lay(flat, routed, CAT)
        flat2 = flat_of(mall(belt=", keep=50"))
        again, _l, _c = circuits.lay(flat2, first, CAT)     # the committed layout, laid again
        self.assertEqual(with_attr(again, "logistic"), {"~belts/i0": "transport-belt<50"})
        gone, _l, _c = circuits.lay(flat_of(mall()), again, CAT)
        self.assertEqual(with_attr(gone, "logistic"), {})

    def test_a_limit_is_a_whole_number(self):
        with self.assertRaises(ElabError):
            flat_of(mall(belt=", keep=0"))

    def test_limits_do_not_silence_clog(self):
        src = """
a   = Assembler<recipe=iron-gear-wheel, keep=50> @(2, 2)
b   = Assembler<recipe=iron-stick, keep=50>      @(2, 8)
box = Chest<provider>                            @(10, 5)
net out: a, b -> box
"""
        self.assertIn(("CLOG", "net out"), checks(flat_of(src), "CLOG"))
        self.assertNotIn(("CLOG", "net out"),
                         checks(flat_of(src.replace("net out:", "net out limited:")), "CLOG"))


class GuardTest(unittest.TestCase):
    def test_a_guarded_crafter_sets_its_input_inserters_filters_from_its_ingredients(self):
        _flat, lay, lines, cks = laid(mall(gear=", guard"))
        self.assertEqual(with_attr(lay, "read"), {"gear/m0": "ingredients"})
        hands = with_attr(lay, "filter")
        self.assertEqual(set(hands.values()), {"circuit"})
        self.assertEqual({w.net for w in lay.wires}, {"gear.signals"})
        self.assertEqual({w.b for w in lay.wires} | {w.a for w in lay.wires},
                         {"gear/m0"} | set(hands))
        self.assertTrue(any(line.startswith("gear guard: 1 input inserter carries")
                            for line in lines))
        self.assertEqual(cks, [])

    def test_a_hand_that_cannot_filter_says_so(self):
        src = mall(gear=", guard").replace("@(6, 2)", "@(6, 2)", 1)
        flat = flat_of(src)
        lay, _n = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT, hand="inserter")
        _out, _lines, cks = circuits.lay(flat, r.layout, CAT)
        self.assertEqual([c.code for c in cks], ["GUARD"])
        self.assertIn("can't filter", cks[0].msg)


class WireTest(unittest.TestCase):
    SRC = """
signal stop = signal-S
k    = Constant<signals="stop=1, iron-plate=5">           @(0, 0)
gate = Assembler<recipe=iron-gear-wheel>                  @(3, 0) when ctl.stop > 0
wire ctl red: k -> gate
"""

    def test_a_machine_enabled_by_a_wire_from_a_constant_combinator(self):
        _flat, lay, lines, cks = laid(self.SRC)
        self.assertEqual(lay.entities["k/m0"].attrs["signals"], "signal-S:1|iron-plate:5")
        self.assertEqual(lay.entities["gate/m0"].attrs["if"], "signal-S>0")
        self.assertEqual(lay.wires, [fkp.Wire("ctl", "red", "gate/m0", "k/m0")])
        self.assertIn("wire ctl red: 2 entities, 1 wire", lines)
        self.assertEqual(cks, [])

    def test_a_signal_no_driver_makes_and_an_unknown_one(self):
        flat = flat_of(self.SRC.replace("ctl.stop > 0", "ctl.signal-Q > 0"))
        sig, = [c for c in flat.checks if c.code == "SIGNAL"]
        self.assertIn("no driver on ctl puts signal-Q on it", sig.msg)
        flat = flat_of(self.SRC.replace("ctl.stop > 0", "ctl.nonsense > 0"))
        self.assertIn("nonsense is no declared signal and no game signal",
                      " ".join(c.msg for c in flat.checks if c.code == "SIGNAL"))

    def test_a_wire_nothing_reads(self):
        flat = flat_of(self.SRC.replace(" when ctl.stop > 0", "").replace("k -> gate", "k"))
        self.assertEqual(checks(flat, "WIRE"), [("WIRE", "wire ctl")])

    def test_auto_signals_come_from_the_pool(self):
        flat = flat_of("signal a\nsignal b = down-arrow\n" + self.SRC)
        self.assertEqual(flat.circuit.autos, {"a": circuits.auto_pool()[1]})

    def test_a_wire_too_long_is_a_wire_reach_line(self):
        _flat, _lay, _lines, cks = laid(self.SRC.replace("@(3, 0)", "@(30, 0)"))
        self.assertEqual([c.code for c in cks], ["WIRE_REACH"])

    def test_two_red_nets_with_other_drivers_on_one_entity_leak(self):
        src = self.SRC + """
k2   = Constant<signals="signal-B=1"> @(0, 2)
wire ctl2 red: k2 -> gate
"""
        _flat, _lay, _lines, cks = laid(src)
        self.assertIn("WIRE_LEAK", [c.code for c in cks])

    BELT = """
src  = Chest<requester, item=iron-plate, rate=1/s> @(0, 0)
dst  = Assembler<recipe=iron-gear-wheel>           @(10, 0)
gate = Assembler<recipe=iron-stick>                @(10, 6) when jam.iron-plate > 5
net feed: src -> dst
wire jam red: feed -> gate
"""

    def test_a_net_drives_a_wire_by_a_belt_that_reads_it(self):
        _flat, lay, _lines, cks = laid(self.BELT)
        belt, = [k for k, v in with_attr(lay, "read").items() if v == "hold"]
        self.assertEqual(lay.entities[belt].attrs["net"], "feed")
        self.assertIn(belt, {w.a for w in lay.wires} | {w.b for w in lay.wires})
        self.assertEqual(cks, [])

    def test_a_belt_on_no_wire_keeps_no_reading_in_the_game(self):
        src = self.BELT.replace(" when jam.iron-plate > 5", "").replace("feed -> gate", "feed")
        _flat, _lay, _lines, cks = laid(src)
        self.assertEqual([c.code for c in cks], ["WIRE"])
        self.assertIn("a belt that is on no wire", cks[0].msg)

    def test_a_network_condition_on_a_machine(self):
        _flat, lay, _lines, cks = laid("g = Assembler<recipe=iron-gear-wheel> @(0, 0) "
                                       "when network.iron-gear-wheel < 100\n")
        self.assertEqual(lay.entities["g/m0"].attrs["logistic"], "iron-gear-wheel<100")
        self.assertEqual(lay.wires, [])


class GatedNetTest(unittest.TestCase):
    SRC = """
signal low = signal-L
src  = Chest<requester, item=iron-plate, rate=1/s> @(0, 0)
dst  = Assembler<recipe=iron-gear-wheel>           @(2, 0)
k    = Constant<signals="low=1">                   @(0, 4)
net feed: src -> dst  when ctl.low > 0
wire ctl red: k -> feed
"""

    def test_every_inserter_of_a_gated_net_takes_the_condition_and_joins_the_wire(self):
        flat, lay, lines, cks = laid(self.SRC)
        self.assertEqual(with_attr(lay, "if"), {"~feed/i0": "signal-L>0"})
        self.assertEqual(lay.wires, [fkp.Wire("ctl", "red", "k/m0", "~feed/i0")])
        self.assertIn(("GATED", "net feed"), checks(flat, "GATED"))   # no behave cycle
        self.assertEqual(cks, [])

    def test_a_behave_cycle_on_its_wire_answers_gated(self):
        flat = flat_of(self.SRC + "behave b on ctl {\n  cycle open: 1 s on, 1 s off\n}\n")
        self.assertEqual(checks(flat, "GATED"), [])

    def test_an_instance_condition_reads_it_on_a_wire_of_its_own(self):
        src = self.SRC.replace("when ctl.low > 0", "when src.iron-plate > 10").replace(
            "wire ctl red: k -> feed", "")
        _flat, lay, _lines, _cks = laid(src)
        self.assertEqual(with_attr(lay, "if"), {"~feed/i0": "iron-plate>10"})
        self.assertEqual({w.net for w in lay.wires}, {"src.signals"})


class CodecTest(unittest.TestCase):
    def test_the_settings_and_wires_go_into_the_blueprint_and_come_back(self):
        text = """fkp 1 factory plant
size 16x16
wire fuel_ctl red
w fuel_ctl red ~fuel/i0 reactor/m0
e reactor/m0 nuclear-reactor 4.5,7.5 read=temperature signal=signal-T
e ~fuel/i0 inserter 1.5,6.5 W net=fuel if=signal-T<550
e ~o/i0 fast-inserter 1.5,9.5 E net=o filter=circuit logistic=iron-gear-wheel>=100
"""
        lay = fkp.loads(text)
        bp = codec.fkp_to_blueprint(lay, CAT)
        ents, wires = bp_entities(bp)
        by = {e["tags"]["src"]: e for e in ents}
        # the plant's own settings, as plant-w3.json has them
        self.assertEqual(by["~fuel/i0"]["control_behavior"], {
            "circuit_enabled": True, "circuit_condition": {
                "first_signal": {"type": "virtual", "name": "signal-T"}, "constant": 550,
                "comparator": "<"}})
        self.assertEqual(by["reactor/m0"]["control_behavior"], {
            "read_temperature": True, "temperature_signal": {"type": "virtual",
                                                             "name": "signal-T"}})
        self.assertEqual(by["~o/i0"]["control_behavior"]["logistic_condition"]["comparator"], "≥")
        self.assertTrue(by["~o/i0"]["use_filters"])
        self.assertEqual(wires, [[1, 1, 2, 1]])
        self.assertEqual(fkp.dumps(codec.blueprint_to_fkp(bp)), fkp.dumps(lay))

    def test_a_blueprint_without_the_typed_settings_keeps_its_config(self):
        rows = [{"src": "x/i0", "name": "inserter", "x": 0.5, "y": 0.5, "direction": 0,
                 "attrs": {"config": codec.config_text({"control_behavior": {
                     "circuit_enabled": True}})}}]
        back, _desc = codec.read_blueprint(codec.blueprint(rows))
        self.assertIn("control_behavior", back[0]["attrs"]["config"])

    def test_a_belt_reads_by_the_keys_the_game_keeps(self):
        # measured on a laptop test server (2.0.77, the lead engineer, 2026-10-22): read_contents
        # arrived false; these come back as written
        self.assertEqual(codec.control_behavior({"read": "hold"}), {"control_behavior": {
            "circuit_read_hand_contents": True, "circuit_contents_read_mode": 1}})
        self.assertEqual(codec.control_behavior({"read": "pulse"})["control_behavior"]
                         ["circuit_contents_read_mode"], 0)

    def game_export(self, attrs, change=None):
        """A one-entity blueprint as the game exports it: its tags kept, an item signal's type
        dropped (the game's default); ``change`` edits its control_behavior first."""
        lay = fkp.loads("fkp 1 factory f\nsize 4x4\n")
        lay.add(fkp.Entity("~n/i0", "fast-inserter", 1.5, 1.5, 4, dict({"net": "n"}, **attrs)))
        bp = json.loads(zlib.decompress(base64.b64decode(codec.fkp_to_blueprint(lay)[1:])))
        cb = bp["blueprint"]["entities"][0]["control_behavior"]
        for cond in ("logistic_condition", "circuit_condition"):
            if cond in cb:
                cb[cond]["first_signal"].pop("type")
        if change:
            change(cb)
        text = json.dumps(bp, separators=(",", ":"))
        return codec.blueprint_to_fkp("0" + base64.b64encode(zlib.compress(
            text.encode())).decode()).entities["~n/i0"].attrs

    def test_a_game_export_without_the_item_type_reads_back_as_written(self):
        got = self.game_export({"logistic": "iron-plate<100"})
        self.assertEqual(got.get("logistic"), "iron-plate<100")
        self.assertNotIn("config", got)

    def test_settings_changed_in_the_game_win_over_the_tags(self):
        got = self.game_export({"logistic": "iron-plate<100"},
                               lambda cb: cb["logistic_condition"].update(constant=40))
        self.assertNotIn("logistic", got)
        self.assertEqual(json.loads(got["config"])["control_behavior"]["logistic_condition"]
                         ["constant"], 40)

    def test_a_constant_combinator_sends_with_quality(self):
        f = codec.control_behavior({"signals": "signal-A:1|iron-plate:5"})
        rows = f["control_behavior"]["sections"]["sections"][0]["filters"]
        self.assertEqual([(r["type"], r["name"], r["quality"], r["count"]) for r in rows],
                         [("virtual", "signal-A", "normal", 1), ("item", "iron-plate", "normal",
                                                                5)])


class RelayTest(unittest.TestCase):
    """A paste over a standing entity didn't take its new settings in the 2039 run ("a limit
    change is not re-pasted"): the record's signature says what was pasted, and an entity whose
    circuit settings changed is ordered up so the paste lays it fresh."""

    def setUp(self):
        from tests.test_sense import surface, live_as_designed
        self.s = surface()
        self.rec = own.rows_of(self.s)
        self.live = copy.deepcopy(live_as_designed(self.s))
        self.key = next(k for k, e in sorted(self.s.entities.items())
                        if CAT.kind(e.name) == "inserter")

    def changed(self):
        s = copy.deepcopy(self.s)
        s.entities[self.key].attrs["logistic"] = "iron-plate<100"
        return s

    def test_a_new_limit_is_laid_fresh_and_an_unchanged_design_is_not(self):
        from tests.test_sense import AREA, WATCH
        from fkcore import sense
        rep = sense.sense(self.s, self.live, CAT, AREA, WATCH, own=self.rec)
        self.assertEqual(own.resettled(self.rec, self.s, rep.verdicts), [])
        s = self.changed()
        got = own.resettled(self.rec, s, sense.sense(s, self.live, CAT, AREA, WATCH,
                                                     own=self.rec).verdicts)
        self.assertEqual([v.key for v in got], [self.key])

    def test_a_record_from_before_signatures_lays_nothing_fresh(self):
        old = {k: own.Row(r.key, r.name, r.x, r.y, r.dir, r.net, own.UNKNOWN)
               for k, r in self.rec.items()}
        from tests.test_sense import AREA, WATCH
        from fkcore import sense
        s = self.changed()
        self.assertEqual(own.resettled(old, s, sense.sense(s, self.live, CAT, AREA, WATCH,
                                                           own=old).verdicts), [])

    def test_the_apply_orders_it_up_before_the_paste(self):
        from tests.test_own import FakeRcon, snapshot_of
        from tests.test_sense import NETS, WATCH
        r = FakeRcon()
        s = self.changed()
        with mock.patch.object(link, "snapshot", snapshot_of(self.live)), \
                mock.patch.object(link, "paste", lambda *a, **k: "0"):
            rep = applymod.apply(r, s, CAT, None, mode="play", policy=WATCH, net_items=NETS,
                                 own=self.rec)
        e = s.entities[self.key]
        self.assertEqual(r.ordered, [(e.name, e.x, e.y)])
        self.assertEqual(len(rep.resettled), 1)
        self.assertIn("1 with new circuit settings", "\n".join(rep.lines()))
        self.assertIsNotNone(rep.own[own.at(e.name, e.x, e.y)].sig)

    def test_the_record_keeps_signatures_on_disk(self):
        import os
        import shutil
        import tempfile
        d = tempfile.mkdtemp(prefix="fkcirc-")
        self.addCleanup(shutil.rmtree, d, True)
        rec = own.rows_of(self.changed())
        own.save(d, "nauvis", rec)
        self.assertEqual(own.load(d, "nauvis"), rec)
        with open(own.path(d, "nauvis"), encoding="utf-8") as fh:
            self.assertIn('"sigs": true', fh.read())
        self.assertTrue(os.path.exists(own.path(d, "nauvis")))


class ComposeTest(unittest.TestCase):
    def test_wires_reach_the_surface_and_the_paste(self):
        from fkcore import compose
        fac = fkp.loads("""fkp 1 factory mall
size 6x2
wire w red
w w red a/c0 ~n/i0
e a/c0 iron-chest 0.5,0.5
e ~n/i0 inserter 1.5,0.5 E net=n if=iron-plate<5
""")
        surf = fkp.loads("fkp 1 surface nauvis\nplot mall at 10,10 rot 0 size 6x2\n")
        s = compose.compose(surf, {"mall": fac}, CAT)
        self.assertEqual(s.wires, [fkp.Wire("mall/w", "red", "nauvis:mall/a/c0",
                                            "nauvis:mall/~n/i0")])
        rows = applymod.scope_rows(s)
        _ents, wires = bp_entities(applymod.paste_blueprint(rows, s, CAT))
        self.assertEqual(wires, [[1, 1, 2, 1]])


if __name__ == "__main__":
    unittest.main()
