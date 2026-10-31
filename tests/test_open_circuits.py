"""2.1, open circuits (PLAN-2.1 "Circuits that reach any building", Rory 2026-10-31): raw cb. and
bp. settings, kinds that carry them, signals from the game, any building with a connector on a
wire, and drift seen on raw fields. Wires carried on poles are in test_circuits.WireTest."""
import json
import unittest

from fkcore import circuits, codec, expand, fkp, lang, route, settings
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate

CAT = Catalog.load()


def flat_of(src):
    f = lang.parse(src, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def laid(src):
    flat = flat_of(src)
    lay, _notes = expand.expand_factory(flat, CAT)
    r = route.route_layout(flat, lay, CAT)
    out, lines, cks = circuits.lay(flat, r.layout, CAT)
    return flat, out, lines, cks


def raw(lay, key, which):
    return json.loads(lay.entities[key].attrs.get(which) or "{}")


class ParseTest(unittest.TestCase):
    def test_raw_values_parse_as_json(self):
        f = lang.parse('set x: cb.a=5, cb.b=-2.5, cb.c=true, cb.d=false, bp.e="two words", '
                       'bp.f=signal-C, bp.g={r: 1, "g": 0.5, b: [1, 2, {k: x}]}, bp.h=[], '
                       'bp.i={}\n', "t.fk")
        p, = f.body.sets
        got = {k: v.value for k, v in p.attrs.items()}
        self.assertEqual(got, {"cb.a": 5, "cb.b": -2.5, "cb.c": True, "cb.d": False,
                               "bp.e": "two words", "bp.f": "signal-C",
                               "bp.g": {"r": 1, "g": 0.5, "b": [1, 2, {"k": "x"}]},
                               "bp.h": [], "bp.i": {}})
        self.assertEqual(str(p.attrs["bp.g"]), '{"r":1,"g":0.5,"b":[1,2,{"k":"x"}]}')

    def test_typed_and_raw_properties_mix(self):
        f = lang.parse("set x: if=iron-plate < 5, cb.read_contents=true\n", "t.fk")
        p, = f.body.sets
        self.assertEqual(p.attrs["if"], "iron-plate<5")
        self.assertEqual(p.attrs["cb.read_contents"], lang.Raw(True))

    def test_raw_parameters_on_an_instance_and_a_kind(self):
        f = lang.parse("kind Counter = Entity<name=roboport, cb.read_robot_stats=true,\n"
                       "  cb.available_construction_output_signal=signal-C>\n"
                       "rc = Counter<bp.text=\"a $name stays\"> @(0, 0)\n", "t.fk")
        k = f.kinds["Counter"]
        self.assertEqual(k.params["cb.read_robot_stats"], lang.Raw(True))
        self.assertEqual(k.params["cb.available_construction_output_signal"].value, "signal-C")
        # a $name inside a quoted string is left as written (module parameters fill it)
        self.assertEqual(f.body.insts[0].params["bp.text"].value, "a $name stays")

    def test_bad_raw_values_are_syntax_errors(self):
        for src, msg in (("set x: cb.=1\n", "a blueprint field"),
                         ("set x: cb.a-b=1\n", "a word of letters, digits and _"),
                         ("set x: bp.a={k: 1, k: 2}\n", "key k given twice"),
                         ("set x: bp.a={5: 1}\n", "an object's key is a word"),
                         ("set x: bp.a=@\n", "a raw value is"),
                         ("set x: bp.a=[1 2]\n", "expected ','"),
                         ("set x: cb.a=1, cb.a=2\n", "property cb.a given twice")):
            with self.assertRaises(lang.FkSyntaxError, msg=src) as cm:
                lang.parse(src, "t.fk")
            self.assertIn(msg, str(cm.exception), src)

    def test_a_name_cb_is_still_a_parameter(self):
        f = lang.parse("x = Chest<provider> @(0, 0)\n", "t.fk")
        self.assertEqual(f.body.insts[0].params, {"provider": True})


SPEAKER = """
box  = Chest<storage>                                        @(0, 0)
spk  = Entity<name=programmable-speaker>                      @(3, 0)
wire stock red: box -> spk
"""


class RawSettingsTest(unittest.TestCase):
    def test_a_condition_string_and_a_signal_name_take_the_games_form(self):
        _f, lay, lines, cks = laid(SPEAKER + 'set spk: cb.circuit_condition="iron-plate<50", '
                                   "bp.alert_parameters={show_alert: true, icon_signal_id: "
                                   'signal-alarm, alert_message: "low"}\n')
        self.assertEqual(cks, [])
        self.assertEqual(raw(lay, "spk/m0", "cb"), {"circuit_condition": {
            "comparator": "<", "constant": 50,
            "first_signal": {"type": "item", "name": "iron-plate"}}})
        self.assertEqual(raw(lay, "spk/m0", "bp"), {"alert_parameters": {
            "show_alert": True, "alert_message": "low",
            "icon_signal_id": {"type": "virtual", "name": "signal-alarm"}}})
        self.assertTrue(any(ln.startswith("set spk: cb.circuit_condition=") for ln in lines))

    def test_raw_settings_survive_the_fkp(self):
        _f, lay, _l, _c = laid(SPEAKER + "set spk: bp.alert_parameters={alert_message: "
                               "\"it's low, 'really'\", show_alert: true}\n")
        back = fkp.loads(fkp.dumps(lay, CAT), "t.fkp")
        self.assertEqual(back.entities["spk/m0"].attrs, lay.entities["spk/m0"].attrs)
        self.assertEqual(raw(back, "spk/m0", "bp")["alert_parameters"]["alert_message"],
                         "it's low, 'really'")

    def test_an_object_is_taken_as_written(self):
        _f, lay, _l, cks = laid(SPEAKER + "set spk: cb.circuit_condition={first_signal: "
                                "{type: virtual, name: signal-A}, comparator: \">\", constant: 3}\n")
        self.assertEqual(cks, [])
        self.assertEqual(raw(lay, "spk/m0", "cb")["circuit_condition"],
                         {"first_signal": {"type": "virtual", "name": "signal-A"},
                          "comparator": ">", "constant": 3})

    def test_the_codec_writes_cb_into_the_control_behaviour_and_bp_on_the_entity(self):
        _f, lay, _l, _c = laid(SPEAKER + 'set spk: cb.circuit_condition="iron-plate<50", '
                               "bp.parameters={playback_volume: 1, playback_mode: global}\n")
        row = next(r for r in codec.rows_of(lay) if r["src"] == "spk/m0")
        e = codec.entity_json(row, 1)
        self.assertEqual(e["control_behavior"]["circuit_condition"]["constant"], 50)
        self.assertEqual(e["parameters"], {"playback_volume": 1, "playback_mode": "global"})
        # and back: the fields go, the raw attrs come back as written
        text = codec.blueprint([row])
        back, _d = codec.read_blueprint(text)
        self.assertEqual(back[0]["attrs"], row["attrs"])
        # changed in the game: the game's fields win, in config
        doc = json.loads(__import__("zlib").decompress(__import__("base64").b64decode(text[1:])))
        doc["blueprint"]["entities"][0]["parameters"]["playback_volume"] = 0.5
        again = "0" + __import__("base64").b64encode(__import__("zlib").compress(
            json.dumps(doc).encode())).decode()
        back, _d = codec.read_blueprint(again)
        self.assertNotIn("bp", back[0]["attrs"])
        self.assertEqual(json.loads(back[0]["attrs"]["config"])["parameters"]["playback_volume"],
                         0.5)

    def test_a_raw_cb_wins_over_a_typed_setting_and_says_so(self):
        src = """
k    = Constant<signals="signal-A=1"> @(0, 0)
lamp = Entity<name=small-lamp>        @(3, 0) when ctl.signal-A > 0
wire ctl red: k -> lamp
set lamp: cb.circuit_condition="signal-A>5", cb.use_colors=true
"""
        _f, lay, _l, cks = laid(src)
        self.assertEqual([c.code for c in cks], ["CIRCUIT"])
        self.assertIn("cb.circuit_condition and a typed setting", cks[0].msg)
        row = next(r for r in codec.rows_of(lay) if r["src"] == "lamp/m0")
        cb = codec.entity_json(row, 1)["control_behavior"]
        self.assertEqual(cb["circuit_condition"]["constant"], 5)
        self.assertTrue(cb["circuit_enabled"] and cb["use_colors"])

    def test_a_lamp_with_raw_settings_gets_no_reset(self):
        _f, lay, _l, _c = laid("lamp = Entity<name=small-lamp, cb.use_colors=true> @(0, 0)\n")
        row = next(r for r in codec.rows_of(lay) if r["src"] == "lamp/m0")
        self.assertEqual(codec.entity_json(row, 1)["control_behavior"], {"use_colors": True})

    def test_refusals(self):
        cases = (
            ("set spk: bp.name=lamp", "CIRCUIT", "bp.name: the codec writes name"),
            ("set spk: bp.control_behavior={}", "CIRCUIT", "a control behaviour field is cb."),
            ('set spk: cb.circuit_condition="iron-plate<<5"', "CIRCUIT", "a condition is"),
            ('set spk: cb.circuit_condition="nonsense<5"', "no-signal", "nonsense is no game "),
            ('set spk: cb.circuit_condition="signal-unknown<5"', "no-signal",
             "signal-unknown never goes out"),
            ("set spk: cb.some_output_signal=signal-each", "no-signal",
             "signal-each never goes out"),
            ("set spk: cb.x=1\nset spk: cb.x=2", "CIRCUIT", "cb.x is set twice"),
            ("set spk: colour=red", "no-match", "or a raw cb.FIELD or bp.FIELD"),
        )
        for text, code, msg in cases:
            _f, _lay, _l, cks = laid(SPEAKER + text + "\n")
            self.assertEqual([c.code for c in cks], [code], text)
            self.assertIn(msg, cks[0].msg, text)

    def test_a_wildcard_reads_in_a_condition(self):
        _f, _lay, _l, cks = laid(SPEAKER + 'set spk: cb.circuit_condition="signal-anything>0"\n')
        self.assertEqual(cks, [])

    def test_raw_settings_go_on_any_template_and_its_hands(self):
        src = """
src  = Chest<requester, item=iron-plate, rate=1/s, bp.bar=4> @(0, 0)
gear = Assembler<recipe=iron-gear-wheel>                   @(4, 0)
net feed: src -> gear
set gear.in: cb.circuit_read_hand_contents=true
"""
        _f, lay, lines, cks = laid(src)
        self.assertEqual(raw(lay, "src/c0", "bp"), {"bar": 4})
        hands = [k for k, e in lay.entities.items() if "inserter" in e.name]
        self.assertTrue(hands)
        for k in hands:
            self.assertEqual(raw(lay, k, "cb"), {"circuit_read_hand_contents": True})

    def test_a_module_instance_takes_no_raw_setting(self):
        src = "module M {\n  a = Chest<storage> @(0, 0)\n}\nm = M<cb.x=1> @(0, 0)\n"
        with self.assertRaises(ElabError) as cm:
            flat_of(src)
        self.assertIn("not cb.x", str(cm.exception))

    def test_a_changed_raw_setting_is_laid_again_and_a_removed_one_goes(self):
        _f, lay, _l, _c = laid(SPEAKER + "set spk: bp.parameters={playback_volume: 1}\n")
        flat = flat_of(SPEAKER + "set spk: bp.parameters={playback_volume: 0.5}\n")
        again, _l, _c = circuits.lay(flat, lay, CAT)
        self.assertEqual(raw(again, "spk/m0", "bp"), {"parameters": {"playback_volume": 0.5}})
        flat = flat_of(SPEAKER)
        again, _l, _c = circuits.lay(flat, lay, CAT)
        self.assertNotIn("bp", again.entities["spk/m0"].attrs)


class KindsTest(unittest.TestCase):
    def test_the_preludes_presets(self):
        src = """
rc   = RobotCounter      @(0, 0)
lamp = ColourLamp        @(6, 0)
spk  = Alarm             @(9, 0)
note = Display<bp.text="hello"> @(12, 0)
wire w red: rc -> lamp, spk, note
"""
        _f, lay, _l, cks = laid(src)
        self.assertEqual(cks, [])
        self.assertEqual(raw(lay, "rc/m0", "cb"), {"read_items_mode": 0, "read_robot_stats": True})
        self.assertEqual(raw(lay, "lamp/m0", "cb"), {"color_mode": 1, "use_colors": True})
        self.assertEqual(raw(lay, "spk/m0", "bp")["alert_parameters"]["icon_signal_id"],
                         {"type": "virtual", "name": "signal-alert"})
        self.assertEqual(raw(lay, "spk/m0", "cb")["circuit_parameters"]["instrument_id"], 0)
        self.assertEqual(raw(lay, "note/m0", "bp"),
                         {"always_show": True, "show_in_chart": True, "text": "hello"})
        self.assertEqual(len([w for w in lay.wires if w.net == "w"]), 3)

    def test_the_instance_overrides_its_kinds_field(self):
        src = ("kind Counter = Entity<name=roboport, cb.read_robot_stats=true, "
               "cb.available_construction_output_signal=signal-C>\n"
               "rc = Counter<cb.available_construction_output_signal=signal-D> @(0, 0)\n")
        _f, lay, _l, _c = laid(src)
        self.assertEqual(raw(lay, "rc/m0", "cb"), {
            "read_robot_stats": True,
            "available_construction_output_signal": {"type": "virtual", "name": "signal-D"}})


class SignalsTest(unittest.TestCase):
    def test_every_signal_comes_from_the_game(self):
        for name in ("signal-alarm", "fusion-plasma", "basic-oil-processing", "nauvis"):
            self.assertTrue(circuits._known(name, CAT), name)
        self.assertEqual(codec.signal_type("fusion-plasma"), "fluid")
        self.assertEqual(codec.signal_type("signal-alarm"), "virtual")
        pool = circuits.auto_pool()
        self.assertIn("signal-alarm", pool)
        self.assertFalse(set(pool) & circuits.NEVER_SENT)

    def test_a_never_sent_signal_is_refused_where_it_is_written(self):
        src = """
k    = Constant<signals="signal-each=1"> @(0, 0)
gate = Assembler<recipe=iron-gear-wheel> @(3, 0) when ctl.signal-A > 0
wire ctl red: k -> gate
"""
        flat = flat_of(src)
        self.assertIn("signal-each never goes out on a wire",
                      " ".join(c.msg for c in flat.checks if c.code == "no-signal"))
        # read in a condition, a wildcard is fine
        flat = flat_of(src.replace("signal-each=1", "signal-A=1")
                       .replace("ctl.signal-A > 0", "ctl.signal-anything > 0"))
        self.assertEqual([c for c in flat.checks if c.code == "no-signal"], [])

    def test_a_new_virtual_signal_is_a_signal(self):
        flat = flat_of("signal bell = signal-alarm\n" + """
k    = Constant<signals="bell=1"> @(0, 0)
gate = Assembler<recipe=iron-gear-wheel> @(3, 0) when ctl.bell > 0
wire ctl red: k -> gate
""")
        self.assertEqual([c for c in flat.checks if c.code == "no-signal"], [])


class AnyBuildingTest(unittest.TestCase):
    def test_entities_with_connectors_take_wires(self):
        src = """
box  = Chest<storage>                   @(0, 0)
rp   = Entity<name=roboport>            @(3, 0)
lamp = Entity<name=small-lamp>          @(8, 0)
spk  = Entity<name=programmable-speaker> @(10, 0)
note = Entity<name=display-panel>       @(12, 0)
stop = Entity<name=train-stop>          @(14, 0)
wire w red: box -> rp, lamp, spk, note, stop
"""
        _f, lay, lines, cks = laid(src)
        self.assertEqual(cks, [])
        ends = {k for wire in lay.wires for k in (wire.a, wire.b)}
        self.assertEqual(ends, {"box/c0", "rp/m0", "lamp/m0", "spk/m0", "note/m0", "stop/m0"})
        self.assertIn("wire w red: 6 entities, 5 wires", lines)

    def test_a_building_without_a_connector_is_a_no_wire_line(self):
        src = """
box = Chest<storage>        @(0, 0)
bc  = Entity<name=beacon>   @(3, 0)
wire w red: box -> bc
"""
        _f, lay, _l, cks = laid(src)
        self.assertEqual([(c.code, c.msg) for c in cks],
                         [("no-wire", "bc/m0: a beacon has no circuit connector")])
        self.assertEqual(lay.wires, [])


class DriftTest(unittest.TestCase):
    """A raw field changed in the game is a hand edit (fkcore.settings)."""

    def rows(self):
        _f, lay, _l, _c = laid(SPEAKER + 'set spk: cb.circuit_condition="iron-plate<50", '
                               "cb.circuit_parameters={signal_value_is_pitch: false, "
                               "instrument_id: 0, note_id: 6}, bp.parameters={playback_volume: "
                               "0.8, playback_mode: global, allow_polyphony: false}\n")
        return [r for r in codec.rows_of(lay) if r["src"] == "spk/m0"]

    def game(self, volume=0.800000011920929, note=6):
        # as the laptop server exported it (2.0.77, 2026-10-31): float32 volume, defaults filled in
        return {"rows": [{"n": 1, "name": "programmable-speaker", "x": 3.5, "y": 0.5, "e": {
            "entity_number": 1, "name": "programmable-speaker", "position": {"x": 3.5, "y": 0.5},
            "alert_parameters": {"alert_message": "", "show_alert": False, "show_on_map": True},
            "control_behavior": {
                "circuit_condition": {"comparator": "<", "constant": 50,
                                      "first_signal": {"name": "iron-plate"}},
                "circuit_parameters": {"instrument_id": 0, "note_id": note,
                                       "signal_value_is_pitch": False,
                                       "stop_playing_sounds": False}},
            "parameters": {"allow_polyphony": False, "playback_mode": "global",
                           "playback_volume": volume, "volume_controlled_by_signal": False}}}]}

    def drifts(self, **kw):
        rows = self.rows()
        v = type("V", (), {"verdict": "ok", "name": "programmable-speaker", "x": 3.5, "y": 0.5,
                           "key": "t:spk/m0"})()
        return settings.drifts(settings.design(rows, None), settings.live(self.game(**kw)), [v],
                               {})

    def test_as_pasted_is_no_drift(self):
        self.assertEqual(self.drifts(), [])

    def test_a_changed_bp_field_or_cb_field_is_a_hand_edit(self):
        d, = self.drifts(volume=0.5)
        # (a false flag is as good as none, so it isn't said)
        self.assertIn('bp.parameters={"playback_mode":"global","playback_volume":0.5}', d.have)
        self.assertIn('"playback_volume":0.8', d.want)
        d, = self.drifts(note=2)
        self.assertIn('cb.circuit_parameters={"instrument_id":0,"note_id":2', d.have)

    def test_a_roboports_default_signals_are_no_drift(self):
        exported = {"control_behavior": {
            "available_construction_output_signal": {"name": "signal-Z", "type": "virtual"},
            "available_logistic_output_signal": {"name": "signal-X", "type": "virtual"},
            "read_items_mode": 0, "read_robot_stats": True,
            "roboport_count_output_signal": {"name": "signal-R", "type": "virtual"},
            "total_construction_output_signal": {"name": "signal-T", "type": "virtual"},
            "total_logistic_output_signal": {"name": "signal-Y", "type": "virtual"}}}
        self.assertEqual(settings._fields(exported),
                         {"control_behavior": {"read_items_mode": 0, "read_robot_stats": True}})


if __name__ == "__main__":
    unittest.main()
