"""2.1 (PLAN-2.1 G and H): buffers, ``limited "..."``, ``read=hold-all`` and names inside a
Literal. A buffer is a role: a ``Buffer`` chest or a ``module NAME buffer``, an unlimited supply
downstream and an unlimited sink upstream, reported by its derivative."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import capture, circuits, codec, expand, lang, literal, rates, route, settings
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, advice, elaborate

CAT = Catalog.load()


def flat_of(src, path="<t>", modules=None):
    f = lang.parse(src, path)
    return elaborate(f, dict(f.modules, **(modules or {})), CAT)


def codes(flat):
    return sorted(c.code for c in flat.checks)


class LanguageTest(unittest.TestCase):
    def test_limited_takes_a_string(self):
        f = lang.parse('a = Assembler<recipe=iron-gear-wheel>\nb = Chest<provider>\n'
                       'net g limited "one inserter per maker": a -> b\n')
        net, = f.body.nets
        self.assertTrue(net.limited)
        self.assertEqual(net.why, "one inserter per maker")

    def test_a_bare_limited_still_parses(self):
        net, = lang.parse("net g limited: a -> b\n").body.nets
        self.assertEqual((net.limited, net.why), (True, None))

    def test_an_empty_string_is_refused(self):
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse('net g limited "": a -> b\n')
        self.assertIn("say what limits the net", str(cm.exception))

    def test_a_module_marked_buffer(self):
        f = lang.parse("module E buffer { }\nmodule F size 3x3 buffer { }\n"
                       "module G buffer size 2x2 { }\nmodule H { }\n")
        self.assertEqual({n: m.buffer for n, m in f.modules.items()},
                         {"E": True, "F": True, "G": True, "H": False})
        self.assertEqual(f.modules["G"].size, (2, 2))

    def test_a_module_with_parameters_marked_buffer(self):
        # 2.1.8: module parameters (2.1.7) come first, then buffer, before or after the size
        f = lang.parse("module E<p> buffer size 3x3 { }\nmodule F<p, q=1> size 3x3 buffer { }\n"
                       "module G<p> { }\n")
        self.assertEqual({n: (m.buffer, [x.name for x in m.params], m.size)
                          for n, m in f.modules.items()},
                         {"E": (True, ["p"], (3, 3)), "F": (True, ["p", "q"], (3, 3)),
                          "G": (False, ["p"], None)})

    def test_buffer_twice_is_refused(self):
        with self.assertRaises(lang.FkSyntaxError):
            lang.parse("module E buffer size 3x3 buffer { }\n")


LINE = """
iron  = MinerRow<n=4, resource=iron-ore>
b     = Buffer<bar=10>
f     = SmelterRow<n=4, ore=iron-ore, machine=electric-furnace>
out   = Chest<provider, limit=10>
net ore: iron -> b
net ore2: b -> f
net pl: f -> out
"""


class BufferChestTest(unittest.TestCase):
    def test_buffer_is_a_steel_chest_off_the_network(self):
        flat = flat_of(LINE)
        inst = flat.insts["b"]
        # 2.1.8: the prelude's kind Buffer = Chest<plain, hold, chest=steel-chest>
        self.assertEqual((inst.kind, inst.core), ("Buffer", "Chest"))
        self.assertEqual(inst.params, {"bar": 10})
        self.assertEqual(inst.kparams, {"plain": True, "hold": True, "chest": "steel-chest",
                                        "bar": 10})
        m = flat.machines["b/c0"]
        self.assertEqual((m.prototype, m.sink, m.source, m.drain), ("steel-chest", True, True, None))
        self.assertEqual(m.extra, {"role": "plain", "buffer": True, "limit": 10})
        self.assertEqual(m.makes, {"iron-ore": float("inf")})      # what fills it
        self.assertEqual(flat.buffers, {"b": "chest"})

    def test_a_buffer_in_the_middle_drives_what_fills_it(self):
        # 20261030-2352, ~2585k: "driver gbuf makes no electronic-circuit"
        src = """
asm  = Assembler<recipe=electronic-circuit>
c    = Chest<requester, item=copper-cable, rate=3/s>
i    = Chest<requester, item=iron-plate, rate=1/s>
gbuf = Buffer
red  = Assembler<recipe=inserter>
g    = Chest<requester, item=iron-gear-wheel, rate=1/s>
out  = Chest<provider, limit=10>
net cab: c -> asm
net fe: i -> asm, red
net ec: asm -> gbuf
net ec2: gbuf -> red
net gw: g -> red
net done: red -> out
"""
        flat = flat_of(src)
        self.assertNotIn("cannot-carry", codes(flat))
        self.assertEqual(flat.nets["ec2"].drivers, [("gbuf/c0", "electronic-circuit")])
        flat2 = flat_of(src.replace("gbuf = Buffer", "gbuf = Chest<plain>"))
        self.assertIn("driver gbuf makes no item", [c.msg for c in flat2.checks
                                                    if c.code == "cannot-carry"])

    def test_buffers_chain_and_item_is_explicit(self):
        flat = flat_of("""
a = Assembler<recipe=iron-gear-wheel>
i = Chest<requester, item=iron-plate, rate=1/s>
b1 = Buffer
b2 = Buffer
b3 = Buffer<item=copper-plate|iron-plate, chest=wooden-chest>
net fe: i -> a
net g: a -> b1
net g2: b1 -> b2
""")
        self.assertEqual(set(flat.machines["b2/c0"].makes), {"iron-gear-wheel"})
        self.assertEqual(flat.machines["b3/c0"].takes, frozenset({"copper-plate", "iron-plate"}))
        self.assertEqual(flat.machines["b3/c0"].prototype, "wooden-chest")

    def test_refusals(self):
        for src, want in (
                ("b = Buffer<rate=1/s>\n", "a buffer takes chest=, item= and bar=, not rate="),
                ("b = Buffer<provider>\n", "one role only: provider, plain"),
                ("b = Chest<hold, provider>\n", "a buffer is a plain chest"),
                ("b = Chest<hold, rate=1/s>\n", "not rate="),
                ("b = Chest<plain, bar=5, limit=5>\n", "bar= and limit= are one setting"),
                ("b = Chest<hold=yes>\n", "hold is a flag")):
            with self.assertRaises(ElabError, msg=src) as cm:
                flat_of(src)
            self.assertIn(want, str(cm.exception), src)

    def test_a_buffer_draws_no_no_taker_and_no_no_rate(self):
        flat = flat_of("iron = MinerRow<n=2, resource=iron-ore>\nb = Buffer\nnet ore: iron -> b\n")
        self.assertEqual(codes(flat), [])

    def test_the_derivative(self):
        model = rates.solve(flat_of(LINE))
        # 4 electric drills make 2/s; 4 electric furnaces take 2.5/s: draining 0.5/s
        self.assertEqual(model.buffers, {"b": {"iron-ore": (2.0, 2.5)}})
        self.assertAlmostEqual(model.inst_rate("b"), 2.5)
        self.assertEqual(model.util[flat_of(LINE).insts["f"].machines[0]], 1.0)  # fed as if never dry
        self.assertEqual(rates.buffer_lines(model),
                         ["BUFFER b: -30.0/min iron-ore (draining: in 120.0, out 150.0)"])
        text = rates.report(model)
        self.assertIn("  BUFFER b: -30.0/min iron-ore (draining", text)
        self.assertIn("buffer (BUFFER below)", text)

    def test_a_mine_into_a_buffer_is_filling(self):
        model = rates.solve(flat_of("iron = MinerRow<n=4, resource=iron-ore>\nb = Buffer\n"
                                    "net ore: iron -> b\n"))
        self.assertEqual(rates.buffer_lines(model),
                         ["BUFFER b: +120.0/min iron-ore (filling: in 120.0, out 0.0)"])

    def test_the_makers_are_never_blocked_by_it(self):
        flat = flat_of(LINE.replace("n=4, ore", "n=1, ore"))
        model = rates.solve(flat)
        self.assertEqual(model.util["iron/m0"], 1.0)
        self.assertEqual(rates.buffer_lines(model),
                         ["BUFFER b: +82.5/min iron-ore (filling: in 120.0, out 37.5)"])

    def test_drivers_cover_first_and_the_buffer_the_rest(self):
        src = LINE + "pit = MinerRow<n=2, resource=iron-ore>\nnet ore3: pit -> f\n"
        src = src.replace("net ore2: b -> f", "net ore2: b, pit -> f").replace(
            "net ore3: pit -> f\n", "")
        model = rates.solve(flat_of(src))
        self.assertEqual(model.buffers["b"]["iron-ore"], (2.0, 1.5))

    def test_an_unbounded_source_fills_it_without_end(self):
        model = rates.solve(flat_of("r = Chest<requester, item=iron-plate>\nb = Buffer\n"
                                    "net p: r -> b\n"))
        self.assertIn("+unbounded/min iron-plate", rates.buffer_lines(model)[0])

    def test_a_gated_source_tops_up_what_goes_out(self):
        model = rates.solve(flat_of(
            "r = Chest<requester, item=iron-plate>\nb = Buffer\n"
            "a = Assembler<recipe=iron-gear-wheel>\no = Chest<provider>\n"
            "wire bw red: b\nnet p: r -> b when bw.iron-plate < 40\n"
            "net f: b -> a\nnet g: a -> o\n"))
        self.assertEqual(model.buffers["b"]["iron-plate"], (2.0, 2.0))
        self.assertEqual(rates.buffer_lines(model),
                         ["BUFFER b: +0.0/min iron-plate (steady, its gated sources top up what "
                          "goes out: in 120.0, out 120.0)"])

    def test_no_buffer_no_line(self):
        model = rates.solve(flat_of("a = Assembler<recipe=iron-gear-wheel>\n"
                                    "i = Chest<requester, item=iron-plate, rate=1/s>\n"
                                    "o = Chest<provider>\nnet f: i -> a\nnet g: a -> o\n"))
        self.assertEqual(model.buffers, {})
        self.assertNotIn("BUFFER", rates.report(model))


MODULE = """
module LoopEnd buffer size 3x3 {
  port i : in iron-plate, copper-cable @w1
  port o : out iron-plate, copper-cable @e1
  net t limited "a belt through": i -> o
}
s1 = Chest<requester, item=iron-plate, rate=1/s>
s2 = Chest<requester, item=copper-cable, rate=2/s>
e = LoopEnd
a = Assembler<recipe=electronic-circuit>
out = Chest<provider, limit=10>
net feed limited "the end buffer gates the sources": s1, s2 -> e.i
net loop limited: e.o -> a
net ec: a -> out
"""


class BufferModuleTest(unittest.TestCase):
    def test_its_ports_are_the_buffer(self):
        flat = flat_of(MODULE)
        self.assertEqual(flat.buffers, {"e": "module"})
        self.assertEqual(flat.machines["e/i"].extra["buffer"], "e")
        model = rates.solve(flat)
        self.assertEqual(model.util["a/m0"], 1.0)
        self.assertEqual(model.buffers, {"e": {"iron-plate": (1.0, 1.0),
                                               "copper-cable": (2.0, 3.0)}})
        self.assertEqual(rates.buffer_lines(model), [
            "BUFFER e: -60.0/min copper-cable (draining: in 120.0, out 180.0)",
            "BUFFER e: +0.0/min iron-plate (steady: in 60.0, out 60.0)"])

    def test_a_parameterised_buffer_module(self):
        src = (MODULE.replace("module LoopEnd buffer size 3x3 {",
                              "module LoopEnd<a, b> buffer size 3x3 {")
               .replace("port i : in iron-plate, copper-cable", "port i : in $a, $b")
               .replace("port o : out iron-plate, copper-cable", "port o : out $a, $b")
               .replace("e = LoopEnd\n", "e = LoopEnd<a=iron-plate, b=copper-cable>\n"))
        flat = flat_of(src)
        self.assertEqual(flat.buffers, {"e": "module"})
        self.assertEqual(rates.buffer_lines(rates.solve(flat)), [
            "BUFFER e: -60.0/min copper-cable (draining: in 120.0, out 180.0)",
            "BUFFER e: +0.0/min iron-plate (steady: in 60.0, out 60.0)"])

    def test_a_chest_inside_a_buffer_module_is_its_inside(self):
        src = MODULE.replace('net t limited "a belt through": i -> o',
                             "box = Buffer\n  net t1: i -> box\n  net t2: box -> o")
        model = rates.solve(flat_of(src))
        self.assertEqual(sorted(model.buffers), ["e"])

    def test_a_buffer_module_needs_ports(self):
        with self.assertRaises(ElabError) as cm:
            flat_of("module E buffer { b = Buffer }\ne = E\n")
        self.assertIn("a buffer's ends are its ports", str(cm.exception))


class LimitedTest(unittest.TestCase):
    SUSHI = """
a = Assembler<recipe=iron-gear-wheel>
b = Assembler<recipe=copper-cable>
box = Chest<provider>
net mix{lim}: a, b -> box
"""

    def test_the_string_stands_where_clog_would(self):
        flat = flat_of(self.SUSHI.format(lim=' limited "each maker has one slot of output"'))
        lines = [(c.code, c.where, c.msg) for c in flat.checks if c.code in ("CLOG", "limited")]
        self.assertEqual(lines, [("limited", "net mix", "each maker has one slot of output")])
        self.assertEqual(advice(flat), [])
        self.assertIn("limited   each maker has one slot of output",
                      expand.explain_net(flat, "mix"))

    def test_a_bare_limited_is_asked_for_its_string(self):
        flat = flat_of(self.SUSHI.format(lim=" limited"))
        self.assertNotIn("limited", codes(flat))
        self.assertNotIn("CLOG", codes(flat))
        a, = advice(flat)
        self.assertEqual((a.code, a.where), ("limited-why", "net mix"))
        self.assertIn('limited "', a.msg)
        self.assertIn("no reason given", expand.explain_net(flat, "mix"))

    def test_without_limited_clog_stays(self):
        flat = flat_of(self.SUSHI.format(lim=""))
        self.assertIn("CLOG", codes(flat))
        self.assertEqual(advice(flat), [])

    def test_explain_of_an_instance_names_its_limited_nets(self):
        flat = flat_of(self.SUSHI.format(lim=' limited "one slot each"') + "\n")
        lay, _notes = expand.expand_factory(flat, CAT)
        self.assertIn("limited   net mix: one slot each", expand.explain(flat, lay, "box", CAT))

    LOOP = """
fe = Chest<requester, item=iron-plate>
cu = Chest<requester, item=copper-plate>
e  = Buffer
g  = Assembler<recipe=iron-gear-wheel>
c  = Assembler<recipe=copper-cable>
box = Chest<provider>
net s: fe, cu -> e
net loop{lim}: e -> g, c
net out: g, c -> box
"""

    def test_a_sushi_loop_from_a_buffer_gets_clog_only(self):
        flat = flat_of(self.LOOP.format(lim=""))
        self.assertNotIn("SUSHI_SINK", codes(flat))
        self.assertIn(("CLOG", "net loop"),
                      [(c.code, c.where) for c in flat.checks if c.code == "CLOG"])
        flat = flat_of(self.LOOP.format(lim=' limited "the end buffer takes what passed"'))
        self.assertNotIn("SUSHI_SINK", codes(flat))
        self.assertNotIn(("CLOG", "net loop"),
                         [(c.code, c.where) for c in flat.checks if c.code == "CLOG"])

    def test_sushi_sink_without_a_buffer(self):
        flat = flat_of(self.LOOP.replace("e  = Buffer\n", "").replace("net s: fe, cu -> e\n", "")
                       .replace("e -> g", "fe, cu -> g").format(lim=""))
        self.assertIn("SUSHI_SINK", codes(flat))


class HoldAllTest(unittest.TestCase):
    def test_the_codec_writes_mode_2(self):
        self.assertEqual(codec.control_behavior({"read": "hold-all"}), {"control_behavior": {
            "circuit_read_hand_contents": True, "circuit_contents_read_mode": 2}})
        self.assertEqual(settings.describe({"control_behavior": {
            "circuit_read_hand_contents": True, "circuit_contents_read_mode": 2}}),
            "read=hold-all")

    def test_set_net_read_hold_all(self):
        src = """
src  = Chest<requester, item=iron-plate, rate=1/s> @(0, 0)
dst  = Assembler<recipe=iron-gear-wheel>           @(10, 0)
gate = Assembler<recipe=iron-stick>                @(10, 6) when jam.iron-plate > 5
net feed: src -> dst
wire jam red: feed -> gate
set feed: read=hold-all
"""
        flat = flat_of(src)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        out, lines, cks = circuits.lay(flat, r.layout, CAT)
        reads = {k: e.attrs["read"] for k, e in out.entities.items() if "read" in e.attrs}
        self.assertEqual(list(reads.values()), ["hold-all"])
        self.assertEqual(out.entities[next(iter(reads))].attrs["net"], "feed")
        self.assertEqual(cks, [])
        self.assertTrue(any("reads hold-all" in ln for ln in lines))
        bad = src.replace("read=hold-all", "read=temperature")
        flat = flat_of(bad)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        _out, _lines, cks = circuits.lay(flat, r.layout, CAT)
        self.assertIn("no-match", [c.code for c in cks])


class LiteralNamesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fklitnames-")

    def tearDown(self):
        shutil.rmtree(self.dir, True)

    def write(self, data):
        with open(os.path.join(self.dir, "lit.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    ENTS = [{"name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4},
            {"name": "assembling-machine-1", "x": 2.5, "y": 2.5, "recipe": "iron-gear-wheel"},
            {"name": "assembling-machine-1", "x": 6.5, "y": 2.5, "recipe": "iron-gear-wheel"}]
    SRC = """
fein = Chest<requester, item=iron-plate, rate=1/s> @(0, 8)
lit  = Literal<file="lit.json"> @(6, 4)
gb   = Chest<provider> @(16, 0)
net in: fein -> lit.asm2
net out: lit.asm2 -> gb
"""

    def flat(self, src=SRC):
        path = os.path.join(self.dir, "main.fk")
        f = lang.parse(src, path)
        return elaborate(f, dict(f.modules), CAT)

    def test_a_name_is_a_net_end(self):
        self.write({"entities": self.ENTS, "names": {"asm1": 1, "asm2": 2}})
        flat = self.flat()
        self.assertEqual(flat.literal_names, {"lit": {"asm1": "lit/assembling-machine-10",
                                                      "asm2": "lit/assembling-machine-11"}})
        self.assertEqual(flat.nets["in"].consumers, [("lit/assembling-machine-11", "iron-plate")])
        lay, _notes = expand.expand_factory(flat, CAT)
        jobs = route.jobs(flat, lay, CAT)
        self.assertEqual(jobs["in"].owners[-1], "lit.asm2")
        self.assertEqual([k for k, _r in jobs["in"].taps], ["lit/assembling-machine-11"])
        self.assertEqual([k for k, _r in jobs["out"].sources], ["lit/assembling-machine-11"])
        self.assertIn("name      lit.asm2 = lit/assembling-machine-11",
                      expand.explain(flat, lay, "lit", CAT))

    def test_the_router_reaches_it(self):
        self.write({"entities": self.ENTS, "names": {"asm2": 2}})
        flat = self.flat()
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        laid = {e.attrs.get("net") for e in r.layout.entities.values() if e.owner.startswith("~")}
        self.assertTrue({"in", "out"} <= laid, laid)

    def test_without_names_it_is_refused_as_before(self):
        self.write({"entities": self.ENTS})
        with self.assertRaises(ElabError) as cm:
            self.flat()
        self.assertIn("names nothing", str(cm.exception))

    def test_a_name_of_no_machine(self):
        self.write({"entities": self.ENTS, "names": {"belt": 0, "asm2": 2}})
        with self.assertRaises(ElabError) as cm:
            self.flat(self.SRC.replace("lit.asm2 -> gb", "lit.belt -> gb"))
        self.assertIn("names a transport-belt of Literal lit, which is no machine", str(cm.exception))

    def test_bad_names(self):
        for names, want in (({"asm-2": 2}, "a word without dashes"),
                            ({"asm2": 7}, "no entity's index (the file has 3"),
                            ({"asm2": "2"}, "no entity's index"),
                            ([1, 2], "maps a name to an entity's index")):
            self.write({"entities": self.ENTS, "names": names})
            with self.assertRaises(ElabError, msg=str(names)) as cm:
                self.flat()
            self.assertIn(want, str(cm.exception), names)

    def test_a_box_keeps_the_index_of_the_file(self):
        self.write({"entities": self.ENTS, "names": {"asm2": 2}})
        path = os.path.join(self.dir, "lit.json")
        ents, _size, _corner = literal.import_entities(path, "lit", CAT, "1,0,9,5")
        self.assertEqual(literal.names_of(path, ents, "1,0,9,5"),
                         {"asm2": "lit/assembling-machine-11"})
        self.write({"entities": self.ENTS, "names": {"belt": 0}})
        with self.assertRaises(literal.LiteralError):
            literal.names_of(path, ents, "1,0,9,5")

    def test_capture_names_the_machines(self):
        names = ["transport-belt", "assembling-machine-2", "stone-furnace", "inserter",
                 "assembling-machine-1", "chemical-plant", "electric-mining-drill", "lab",
                 "wooden-chest"]
        self.assertEqual(capture.names(names, CAT), {"asm1": 1, "furnace1": 2, "asm2": 4,
                                                     "chem1": 5, "drill1": 6, "lab1": 7})
        self.assertEqual(capture.name_span({"asm1": 1, "asm2": 4, "furnace1": 2}),
                         "asm1..asm2, furnace1")
        rows = [{"name": n, "x": 0.5 + 4 * k, "y": 0.5, "direction": 0, "attrs": {}}
                for k, n in enumerate(names[:3])]
        self.assertEqual(capture.names_of_bp(codec.blueprint(rows), CAT),
                         {"asm1": 1, "furnace1": 2})

    def test_a_blueprint_keeps_its_circuit_settings(self):
        rows = [{"name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4,
                 "attrs": {"read": "hold-all"}},
                {"name": "inserter", "x": 0.5, "y": 1.5, "direction": 8,
                 "attrs": {"if": "iron-plate<40"}}]
        red = codec.connector("red")
        self.write({"bp": codec.blueprint(rows, links=[(0, red, 1, red)])})
        got, wires = literal.read_entities(os.path.join(self.dir, "lit.json"))
        self.assertEqual([r[4] for r in got], [{"read": "hold-all"}, {"if": "iron-plate<40"}])
        self.assertEqual(wires, [(0, red, 1, red)])


if __name__ == "__main__":
    unittest.main()
