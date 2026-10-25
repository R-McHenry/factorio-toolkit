"""Rory's 4-belt bus as a template (2026-10-21): ``Bus<belts, length, item, load=, tap=>``.

agent/docs/examples/bus4.json is his demo as he placed it in the lead world: four belts east, a
feeder from the south that merges into all four by a staircase of splitters, two taps that pull out
by staircases, one north, one south. The template at his parameters lays the same bus. A bus is a
net of its own; its loads and taps are ports, the endpoints other nets name. The router routes into
a load and out of a tap and never lays the bus; connect reads a port as a joint, not a LEAK; the
rate model pools every net through the bus; the routed rates see its lanes and its splitters'
priorities.
"""
import json
import os
import unittest

from fkcore import connect, expand, fkp, lang, lanes, literal, rates, route, routed
from fkcore import throughput as tp
from fkcore.catalog import Catalog
from fkcore.elaborate import ADVICE, ElabError, elaborate, elaborate_file
from fkcore.fragments import fragment

CAT = Catalog.load()
INF = float("inf")
EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples")
RORY = {"belts": 4, "length": 54, "item": "iron-plate", "load": "s11", "tap": ["n26", "s33"]}
PLATE = "iron-plate"

# a smelter row loads a bus from the south; gears tap it to the north, a chest to the south
LOADED = """
ore   = Chest<requester, item=iron-ore, rate=2/s>   @(2, 30)
coal  = Chest<requester, item=coal, rate=1/s>       @(2, 34)
smelt = SmelterRow<n=4, recipe=iron-plate>          @(6, 28)
bus   = Bus<belts=4, length=40, item=iron-plate, load=s4, tap=n20|s30> @(0, 14)
gears = AsmRow<n=2, recipe=iron-gear-wheel>         @(14, 2)
gbox  = Chest<provider, limit=4>                    @(26, 4)
pbox  = Chest<provider, limit=4>                    @(34, 26)
net ore_:  ore -> smelt
net fuel:  coal -> smelt
net iron1: smelt -> bus.load1
net fe:    bus.tap1 -> gears
net gear:  gears -> gbox
net spare: bus.tap2 -> pbox
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def laid(text):
    flat = flat_of(text)
    lay, notes = expand.expand_factory(flat, CAT)
    return flat, lay, notes


def bad(test, text, words):
    with test.assertRaises(ElabError) as ctx:
        flat_of(text)
    for w in words:
        test.assertIn(w, str(ctx.exception))


class TemplateTest(unittest.TestCase):
    def test_at_rorys_parameters_it_is_his_demo(self):
        # his ghosts read from the lead world; the template's frame is his y 7..12
        frag = fragment("Bus", dict(RORY), [], [])
        ents = frag.entities
        self.assertEqual(frag.size, (54, 6))
        rows, _wires = literal.read_entities(os.path.join(EXAMPLES, "bus4.json"))
        his = {(r[0], r[1], r[2]): r for r in rows}
        mine = {(e.name, e.x, e.y + 7): e for e in ents}
        self.assertEqual(len(mine), 210)                    # 195 belts, 12 splitters, 3 stubs
        self.assertEqual(set(mine) - set(his), set())
        for k, e in mine.items():
            self.assertEqual(his[k][3] or 0, e.dir or 0, k)
            if e.name == "splitter":
                self.assertEqual(json.loads(his[k][4]["config"]), json.loads(e.attrs["config"]), k)
        # his other 17 belts are the feeder's and the taps' beyond the bus: the routes' belts
        rest = sorted((k[1], k[2], his[k][3] or 0) for k in set(his) - set(mine))
        self.assertEqual(len(rest), 17)
        self.assertEqual({(x, d) for x, _y, d in rest}, {(11.5, 0), (26.5, 0), (33.5, 8)})
        self.assertEqual(sorted(frag.roles), ["load1", "pool", "tap1", "tap2"])
        # each port's attach point is its stub, items moving away from the bus or into it
        self.assertEqual(frag.roles["load1"].attach, [(11.5, 5.5, 0)])
        self.assertEqual(frag.roles["tap1"].attach, [(26.5, 0.5, 0)])
        self.assertEqual(frag.roles["tap2"].attach, [(33.5, 5.5, 8)])

    def test_the_staircases_priorities(self):
        frag = fragment("Bus", dict(RORY), [], [])
        prio = {e.local: json.loads(e.attrs["config"]) for e in frag.entities
                if e.name == "splitter"}
        north = {"input_priority": "right", "output_priority": "left"}    # climbs north
        south = {"input_priority": "left", "output_priority": "right"}    # climbs south
        for k in range(4):
            self.assertEqual(prio[f"load1s{k}"], north)     # from the south feeder to belt 1
            self.assertEqual(prio[f"tap1s{k}"], north)      # from belt 4 up to the north tap
            self.assertEqual(prio[f"tap2s{k}"], south)      # from belt 1 down to the south tap

    def test_ports_are_endpoints_and_the_bus_is_a_net(self):
        flat = flat_of(LOADED)
        self.assertEqual([c for c in flat.checks if c.code not in ADVICE], [])
        self.assertEqual(flat.nets["iron1"].consumers, [("bus/load1", PLATE)])
        self.assertEqual(flat.nets["fe"].drivers, [("bus/tap1", PLATE)])
        bus = flat.nets["bus"]
        self.assertEqual((bus.items, bus.drivers, bus.consumers),
                         ([PLATE], [("bus/load1", PLATE)],
                          [("bus/tap1", PLATE), ("bus/tap2", PLATE)]))

    def test_a_port_no_net_names_is_a_spare(self):
        flat = flat_of(LOADED.replace("load=s4,", "load=s4|n10,"))
        self.assertEqual([c for c in flat.checks if c.code not in ADVICE], [])   # no UNFED for load2
        self.assertEqual(flat.nets["bus"].drivers, [("bus/load1", PLATE)])
        _flat, lay, _notes = laid(LOADED.replace("load=s4,", "load=s4|n10,"))
        self.assertIn("bus/load1", lay.entities)
        self.assertNotIn("bus/load2", lay.entities)         # no belt, its staircase only
        self.assertIn("bus/load2s0", lay.entities)

    def test_free_ports_with_star(self):
        flat = flat_of("""
            bus = Bus<length=20, item=iron-plate, load=s2, tap=n12|s18> @(0, 4)
            src = Chest<requester, item=iron-plate, rate=1/s> @(0, 12)
            box = Chest<provider, limit=2> @(14, 0)
            net a: src -> bus.*
            net b: bus.tap1 -> box
            net c: bus.* -> box
        """)
        self.assertEqual(flat.nets["a"].consumers, [("bus/load1", PLATE)])
        self.assertEqual(flat.nets["c"].drivers, [("bus/tap2", PLATE)])

    def test_bad_buses_are_bad_parameters(self):
        base = "bus = Bus<{}> @(0, 0)\n"
        bad(self, base.format("length=20, item=iron-plate, load=s2|n4"), ["overlap", "load n4"])
        bad(self, base.format("length=20, item=iron-plate, tap=n2"),
            ["tap n2", "-2..2", "0..19"])
        bad(self, base.format("length=20, item=iron-plate, load=s2, tap=e12"), ["two sides"])
        bad(self, base.format("length=20, item=iron-plate, load=12"), ["load=12", "e.g. s11"])
        bad(self, base.format("length=20, item=water, load=s2"), ["water is a fluid"])
        bad(self, base.format("item=iron-plate, load=s2"), ["needs length="])
        bad(self, base.format("length=20, item=iron-plate, lanes=2"), ["unknown parameter"])
        bad(self, "bus = Bus<length=20, item=iron-plate> @(0, 0)\nnet bus: bus -> bus\n",
            ["net bus", "name this net otherwise"])

    def test_a_net_brings_the_wrong_item(self):
        flat = flat_of("""
            bus = Bus<length=20, item=iron-plate, load=s2> @(0, 4)
            cu  = Chest<requester, item=copper-plate, rate=1/s> @(0, 12)
            net c: cu -> bus.load1
        """)
        self.assertEqual([c.code for c in flat.checks], ["TYPE"])
        self.assertIn("consumer bus.load1 takes no copper-plate", str(flat.checks[0]))

    def test_turned(self):
        # running south (rot 1) its sides are e and w; a load from the west, a tap to the east
        flat, lay, notes = laid("""
            bus = Bus<belts=2, length=12, item=iron-plate, load=w1, tap=e9> @(4, 0, rot 1)
            src = Chest<requester, item=iron-plate, rate=1/s> @(0, 1)
            box = Chest<provider, limit=2> @(10, 9)
            net a: src -> bus.load1
            net b: bus.tap1 -> box
        """)
        self.assertEqual(notes, [])
        self.assertEqual(expand.frame_of(flat, lay, "bus", CAT), (4, 0, 8, 12))
        self.assertEqual(lay.entities["bus/b1_0"].dir, 8)                   # its belts run south
        self.assertEqual({e.dir for e in lay.entities.values() if e.name == "splitter"}, {8})
        # turned clockwise, its own south is the west: the load's belt on the west column, the
        # route coming from the west; the tap's on the east, the route leaving east
        self.assertEqual((lay.entities["bus/load1"].x, lay.entities["bus/load1"].y), (4.5, 1.5))
        self.assertEqual((lay.entities["bus/tap1"].x, lay.entities["bus/tap1"].y), (7.5, 9.5))
        attach = {role: (x, y, d) for role, _s, _n, (x, y, d)
                  in expand.attach_points(flat, lay, "bus", CAT)}
        self.assertEqual(attach, {"load1": (4.5, 1.5, 4), "tap1": (7.5, 9.5, 4)})
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {}, r.lines)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual((rep.checks, rep.leaks), ([], []))
        # n and s are along it there: the build says so, placing nothing
        _flat, lay, notes = laid("""
            bus = Bus<belts=2, length=12, item=iron-plate, load=s1> @(4, 0, rot 1)
        """)
        self.assertEqual(lay.insts, {})
        self.assertIn("the bus runs south (rot 1): its ports go on its e and w sides, not s",
                      notes[0])

    def test_in_a_turned_module(self):
        # sides are the frame's the bus is written in: a module turned keeps its source
        text = """
            module Iron {
              bus = Bus<belts=2, length=12, item=iron-plate, load=s1, tap=n9> @(0, 4)
              src = Chest<requester, item=iron-plate, rate=1/s> @(0, 10)
              box = Chest<provider, limit=2> @(11, 0)
              net a: src -> bus.load1
              net b: bus.tap1 -> box
            }
            iron = Iron @(0, 0, rot ROT)
        """
        for rot in range(4):
            flat, lay, notes = laid(text.replace("ROT", str(rot)))
            self.assertEqual(notes, [], rot)
            r = route.route_layout(flat, lay, CAT)
            self.assertEqual(r.failed, {}, (rot, r.lines))
            rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
            self.assertEqual((rep.checks, rep.leaks), ([], []), rot)
            # the load's belt points into the staircase's first splitter, turned with it
            stub, s0 = lay.entities["iron/bus/load1"], lay.entities["iron/bus/load1s0"]
            self.assertEqual(stub.dir, s0.dir, rot)
            self.assertEqual(s0.dir, (4 + 4 * rot) % 16, rot)          # east, turned

    def test_explain(self):
        flat, lay, _notes = laid(LOADED)
        text = expand.explain(flat, lay, "bus", CAT)
        self.assertIn("iron-plate on 4 belts, 40 tiles, running east: net bus (its own: 139 "
                      "belts, 12 splitters)", text)
        self.assertIn("in   load1 s4   net iron1          attach 4.5,19.5 N", text)
        self.assertIn("out  tap2  s30  net spare          attach 30.5,19.5 S", text)
        with self.assertRaises(ValueError):
            expand.unfold("", flat, lay, "bus")


class RatesTest(unittest.TestCase):
    """The rate model: a bus is a pool. What the loads bring is what the taps share."""

    TWO = """
        a    = Chest<requester, item=iron-plate, rate=3/s>  @(0, 20)
        b    = Chest<requester, item=iron-plate, rate=2/s>  @(10, 20)
        bus  = Bus<length=40, item=iron-plate, load=s2|s14, tap=n24|n32> @(0, 10)
        g    = AsmRow<n=2, recipe=iron-gear-wheel>          @(20, 0)
        s    = AsmRow<n=2, recipe=iron-stick>               @(30, 0)
        out  = Chest<provider>                              @(0, 0)
        net la: a -> bus.load1
        net lb: b -> bus.load2
        net tg: bus.tap1 -> g
        net ts: bus.tap2 -> s
        net made: g, s -> out
    """

    def test_what_the_loads_bring_the_taps_share(self):
        m = rates.solve(flat_of(self.TWO))
        pool = m.nets[("bus", PLATE)]
        # 5/s in; gears would take 4/s and sticks 2/s: 6 asked, shared by appetite
        self.assertAlmostEqual(pool.supply, 5.0)
        self.assertAlmostEqual(pool.would_take, 6.0)
        self.assertAlmostEqual(pool.delivered, 5.0)
        self.assertAlmostEqual(m.util["g/m0"], 5 / 6)
        self.assertAlmostEqual(m.util["s/m0"], 5 / 6)
        self.assertEqual(m.binding["g/m0"], ("in", PLATE, "bus"))
        self.assertAlmostEqual(m.nets[("tg", PLATE)].delivered, 4 * 5 / 6)
        self.assertAlmostEqual(m.nets[("ts", PLATE)].delivered, 2 * 5 / 6)
        self.assertAlmostEqual(m.nets[("la", PLATE)].delivered, 3.0)
        self.assertAlmostEqual(m.nets[("lb", PLATE)].delivered, 2.0)
        self.assertAlmostEqual(m.inst_rate("bus"), 5.0)
        self.assertAlmostEqual(m.port_rate("bus/tap1"), 4 * 5 / 6)
        self.assertAlmostEqual(m.port_rate("bus/load2"), 2.0)

    def test_what_the_taps_dont_take_slows_the_loads(self):
        m = rates.solve(flat_of(self.TWO.replace("rate=3/s", "rate=6/s")
                                .replace("rate=2/s", "rate=4/s")))
        # 10/s offered, 6/s taken: both requesters slow alike
        self.assertAlmostEqual(m.nets[("bus", PLATE)].delivered, 6.0)
        self.assertAlmostEqual(m.util["a/c0"], 0.6)
        self.assertAlmostEqual(m.util["b/c0"], 0.6)
        self.assertEqual(m.binding["a/c0"], ("out", PLATE, "bus"))
        self.assertAlmostEqual(m.util["g/m0"], 1.0)

    def test_the_report_and_the_chain(self):
        m = rates.solve(flat_of(self.TWO))
        text = rates.report(m)
        self.assertIn("pool: loads bring 5.000/s, taps would take 6.000/s", text)
        self.assertIn("iron-plate 300.00", text)                    # 5/s through the bus
        chain = rates.chain(m, "g")
        self.assertEqual(chain[0], "g 0.833 (iron-plate short on bus)")
        self.assertEqual(chain[1], "  <- bus iron-plate: supply 5.000/s, consumers would take "
                                   "6.000/s")

    def test_asserts_on_the_bus_and_a_port(self):
        m = rates.solve(flat_of(self.TWO + "assert bus.rate >= 4/s\nassert bus.tap2.rate >= 2/s\n"))
        self.assertEqual([(ok, round(v, 6)) for _t, ok, v, _r, _o in m.asserts],
                         [(True, 5.0), (False, round(2 * 5 / 6, 6))])

    def test_unbounded_what_if_through_the_bus(self):
        m = rates.solve(flat_of(self.TWO), unbounded=["la"])
        self.assertAlmostEqual(m.util["g/m0"], 1.0)
        self.assertAlmostEqual(m.util["s/m0"], 1.0)

    def test_an_unbounded_requester_loads_what_the_taps_take(self):
        m = rates.solve(flat_of(self.TWO.replace(", rate=3/s", "")))
        self.assertAlmostEqual(m.nets[("bus", PLATE)].delivered, 6.0)
        self.assertAlmostEqual(m.nets[("la", PLATE)].delivered, 4.0)      # 6 less b's 2

    def test_a_smelter_row_loads_it(self):
        m = rates.solve(flat_of(LOADED))
        self.assertAlmostEqual(m.nets[("bus", PLATE)].supply, 1.25)      # 4 stone furnaces
        self.assertAlmostEqual(m.util["gears/m0"], 1.25 / 4)
        self.assertAlmostEqual(m.nets[("spare", PLATE)].delivered, 0.0)   # the gears took all


class ConnectTest(unittest.TestCase):
    def setUp(self):
        self.flat, lay, _notes = laid(LOADED)
        self.r = route.route_layout(self.flat, lay, CAT)

    def test_ports_are_joints_not_leaks(self):
        rep = connect.connect(self.r.layout, CAT, connect.endpoints(self.flat))
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {n: "connected" for n in self.flat.nets})
        self.assertEqual(rep.leaks, [])
        self.assertEqual(rep.checks, [])
        self.assertEqual((rep.nets["bus"].pairs, rep.nets["bus"].reached), (2, 2))

    def test_a_belt_into_the_bus_from_elsewhere_still_leaks(self):
        lay = self.r.layout
        bus = lay.insts["bus"]
        lay.add(fkp.Entity("~fuel/b99", "transport-belt", bus.x + 2.5, bus.y + 0.5, 8,
                           {"net": "fuel"}))
        rep = connect.connect(lay, CAT, connect.endpoints(self.flat))
        self.assertEqual([lk.text for lk in rep.leaks],
                         ["~fuel/b99 side-loads onto bus/b1_2 (net bus)"])

    def test_a_load_after_a_tap_never_reaches_it(self):
        flat, lay, _notes = laid("""
            bus = Bus<belts=2, length=30, item=iron-plate, load=s2|s20, tap=n12> @(0, 6)
            a   = Chest<requester, item=iron-plate, rate=1/s> @(0, 14)
            b   = Chest<requester, item=iron-plate, rate=1/s> @(18, 14)
            box = Chest<provider, limit=2> @(14, 0)
            net la: a -> bus.load1
            net lb: b -> bus.load2
            net t:  bus.tap1 -> box
        """)
        r = route.route_layout(flat, lay, CAT)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual(rep.nets["bus"].status, "open")
        self.assertEqual(rep.nets["bus"].unreached, [("bus/load2", "bus/tap1")])
        self.assertEqual(rep.leaks, [])


class RouteTest(unittest.TestCase):
    """The router routes a smelter row into a load and from a tap to a factory; the bus itself is
    the template's and never routed."""

    def test_a_smelter_loads_and_a_factory_taps(self):
        flat, lay, _notes = laid(LOADED)
        before = {k: e for k, e in lay.entities.items() if e.owner == "bus"}
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {}, r.lines)
        self.assertEqual(sorted(r.routed), ["fe", "fuel", "gear", "iron1", "ore_", "spare"])
        self.assertFalse(any(k.startswith("~bus/") for k in r.layout.entities))
        self.assertFalse(any("bus:" in line for line in r.lines))
        after = {k: e for k, e in r.layout.entities.items() if e.owner == "bus"}
        self.assertEqual(after, before)
        self.assertEqual(fkp.invariants(r.layout, CAT, nets=flat.nets), [])
        # the smelter's route ends just south of the load's belt, pointing north into it
        stub = r.layout.entities["bus/load1"]
        last = [e for k, e in r.layout.entities.items() if k.startswith("~iron1/")
                and (e.x, e.y) == (stub.x, stub.y + 1)]
        self.assertEqual([e.dir for e in last], [0])
        # the gears' route starts just north of the tap's belt
        tap = r.layout.entities["bus/tap1"]
        self.assertTrue(any((e.x, e.y) == (tap.x, tap.y - 1) for k, e in r.layout.entities.items()
                            if k.startswith("~fe/")))
        # the routes laid again are kept: a build changes only what changed
        again = route.route_layout(flat, r.layout, CAT)
        self.assertEqual(again.routed, [])

    def test_a_main_bus_of_two_items(self):
        # a second item is a second bus: each one's net from beyond the other crosses it by a
        # yellow underground from one of its outer rows to the other (4 belts between)
        flat, lay, _notes = laid("""
            cu   = Bus<belts=4, length=30, item=copper-plate, load=n2, tap=s20> @(0, 4)
            fe   = Bus<belts=4, length=30, item=iron-plate, load=n2, tap=s14> @(0, 11)
            cin  = Chest<requester, item=copper-plate, rate=1/s> @(0, 0)
            fin  = Chest<requester, item=iron-plate, rate=1/s> @(6, 0)
            wire = AsmRow<n=1, recipe=copper-cable> @(18, 22)
            fbox = Chest<provider, limit=2> @(12, 22)
            cbox = Chest<provider, limit=2> @(24, 22)
            net c1:  cin -> cu.load1
            net f1:  fin -> fe.load1
            net c2:  cu.tap1 -> wire
            net f2:  fe.tap1 -> fbox
            net cab: wire -> cbox
        """)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {}, r.lines)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual((rep.checks, rep.leaks), ([], []))
        tunnels = {e.owner: (e.x, e.y) for e in r.layout.entities.values()
                   if e.name == "underground-belt" and e.attrs["ug"] == "in"}
        self.assertEqual(tunnels["~f1"][1], 4.5)                   # the copper bus's north row
        self.assertEqual(tunnels["~c2"][1], 11.5)                  # the iron bus's north row

    def test_the_example(self):
        flat = elaborate_file(os.path.join(EXAMPLES, "bus4.fk"), CAT)
        # LANES is advice (the example's smelter takes ore and coal by two chests), not a fault
        self.assertEqual([c for c in flat.checks if c.code not in ADVICE], [])
        lay, notes = expand.expand_factory(flat, CAT)
        self.assertEqual(notes, [])
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {}, r.lines)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual(set(x.status for x in rep.nets.values()), {"connected"}, rep.lines())
        self.assertEqual(rep.leaks, [])
        # the bus is his demo's: the same 210 entities where he put them, 10 tiles further down
        rows, _wires = literal.read_entities(os.path.join(EXAMPLES, "bus4.json"))
        his = {(n, x, y) for n, x, y, _d, _s in rows}
        mine = {(e.name, e.x, e.y - 3) for e in lay.entities.values() if e.owner == "bus"}
        self.assertEqual(len(mine), 210)
        self.assertEqual(mine - his, set())
        m = rates.solve(flat)
        self.assertAlmostEqual(m.nets[("bus", PLATE)].delivered, 2.5)    # 8 stone furnaces
        self.assertAlmostEqual(m.util["gears/m0"], 1.0)
        self.assertAlmostEqual(m.nets[("spare", PLATE)].delivered, 0.5)  # the chest the rest


class LaneTest(unittest.TestCase):
    """The V2 lane graph keeps a splitter's priorities (its game settings, ``config``)."""

    def splitter(self, prio):
        rows = ["fkp 1 factory t",
                "e a/x0 transport-belt 0.5,0.5 E net=a", "e a/y0 transport-belt 0.5,1.5 E net=a",
                f"e a/s splitter 1.5,1 E net=a config='{json.dumps(prio)}'",
                "e a/x1 transport-belt 2.5,0.5 E net=a", "e a/y1 transport-belt 2.5,1.5 E net=a"]
        return lanes.build(fkp.loads("\n".join(rows)), CAT)

    def test_priorities_rank_inputs_and_order_outputs(self):
        lg = self.splitter({"input_priority": "right", "output_priority": "left"})
        into = {e.src[0]: e.rank for e in lg.inn[("a/s", "L")]}
        self.assertEqual(into, {"a/y0": 0, "a/x0": 1})        # facing east, right is south
        out = {e.dst[0]: e.first for e in lg.out[("a/s", "L")]}
        self.assertEqual(out, {"a/x1": True, "a/y1": False})  # left is north
        plain = lanes.build(fkp.loads("fkp 1 factory t\ne a/s splitter 1.5,1 E net=a"), CAT)
        self.assertEqual(plain.graph.nodes["a/s"].prio, None)

    def test_the_preferred_output_fills_first(self):
        lg = self.splitter({"output_priority": "left"})
        r = tp.solve(lg, supply={("a/x0", "L"): {PLATE: 5}},
                     demand={("a/x1", "L"): {PLATE: 3}, ("a/y1", "L"): {PLATE: 3}})
        self.assertAlmostEqual(r.delivered[("a/x1", "L")][PLATE], 3.0)
        self.assertAlmostEqual(r.delivered[("a/y1", "L")][PLATE], 2.0)
        even = self.splitter({})
        r = tp.solve(even, supply={("a/x0", "L"): {PLATE: 5}},
                     demand={("a/x1", "L"): {PLATE: 3}, ("a/y1", "L"): {PLATE: 3}})
        self.assertAlmostEqual(r.delivered[("a/y1", "L")][PLATE], 2.5)

    def test_the_preferred_input_goes_first(self):
        lg = self.splitter({"input_priority": "left"})
        r = tp.solve(lg, supply={("a/x0", "L"): {PLATE: 5}, ("a/y0", "L"): {"copper-plate": 5}},
                     demand={("a/x1", "L"): {PLATE: INF, "copper-plate": INF}})
        got = r.delivered[("a/x1", "L")]
        # one lane out (7.5/s): the left input's 5 first, the right's 2.5 after
        self.assertAlmostEqual(got[PLATE], 5.0)
        self.assertAlmostEqual(got["copper-plate"], 2.5)


class BusFlowTest(unittest.TestCase):
    """Rory's bus as laid (V2): his staircases on the lane graph, the feeder and the taps' belts
    as the routes would lay them. A yellow belt carries 15/s across its two lanes."""

    @classmethod
    def setUpClass(cls):
        frag = fragment("Bus", dict(RORY), [], [])
        lay = fkp.Layout("factory", "t")
        for e in frag.entities:
            lay.add(fkp.Entity(f"bus/{e.local}", e.name, e.x, e.y + 10, e.dir,
                               dict(e.attrs, net="bus")))
        # the feeder from the south into the load, the taps' belts out, as in his demo
        for y in range(16, 20):
            lay.add(fkp.Entity(f"f/b{y}", "transport-belt", 11.5, y + 0.5, 0, {"net": "f"}))
        for y in range(4, 10):
            lay.add(fkp.Entity(f"n/b{y}", "transport-belt", 26.5, y + 0.5, 0, {"net": "n"}))
        for y in range(16, 22):
            lay.add(fkp.Entity(f"s/b{y}", "transport-belt", 33.5, y + 0.5, 8, {"net": "s"}))
        cls.lg = lanes.build(lay, CAT)

    def solve(self, feed, north, south):
        supply = {("f/b19", lane): {PLATE: feed} for lane in ("L", "R")}
        demand = {("n/b4", lane): {PLATE: north / 2} for lane in ("L", "R")}
        demand.update({("s/b21", lane): {PLATE: south / 2} for lane in ("L", "R")})
        return tp.solve(self.lg, supply=supply, demand=demand)

    def flow(self, r, key):
        return sum(r.flow.get((key, lane), {}).get(PLATE, 0.0) for lane in ("L", "R"))

    def test_the_load_fills_the_far_belt_first(self):
        r = self.solve(5, 0, INF)               # 10/s in, all of it taken at the south tap
        self.assertAlmostEqual(self.flow(r, "bus/b1_20"), 10.0)     # belt 1, the far one
        for belt in (2, 3, 4):
            self.assertAlmostEqual(self.flow(r, f"bus/b{belt}_20"), 0.0)

    def test_a_full_yellow_belt_is_two_lanes(self):
        r = self.solve(7.5, 0, INF)             # a full feeder: 15/s, both lanes
        self.assertAlmostEqual(self.flow(r, "bus/b1_20"), 15.0)
        self.assertFalse(r.binds(("f/b19", "L")))
        self.assertAlmostEqual(sum(r.delivered.get(("s/b21", l), {}).get(PLATE, 0.0)
                                   for l in ("L", "R")), 15.0)
        r = self.solve(10, 0, INF)              # 20/s offered: the feeder's lanes carry 15
        self.assertAlmostEqual(sum(r.delivered.get(("s/b21", l), {}).get(PLATE, 0.0)
                                   for l in ("L", "R")), 15.0)
        self.assertTrue(r.binds(("f/b19", "L")))

    def test_the_first_tap_takes_its_fill(self):
        r = self.solve(7.5, 6, INF)             # 15/s in: the north tap first, the rest south
        north = sum(r.delivered.get(("n/b4", l), {}).get(PLATE, 0.0) for l in ("L", "R"))
        south = sum(r.delivered.get(("s/b21", l), {}).get(PLATE, 0.0) for l in ("L", "R"))
        self.assertAlmostEqual(north, 6.0)
        self.assertAlmostEqual(south, 9.0)


class RoutedTest(unittest.TestCase):
    """The routed report: a bus port is no machine; CAPACITY names what binds beyond it."""

    def test_port_rows_count_what_crosses_the_belt(self):
        flat, lay, _notes = laid(LOADED)
        r = route.route_layout(flat, lay, CAT)
        rr = routed.solve(flat, r.layout, CAT)
        lines, checks = routed.report(rr, "t")
        rows = {l.split()[0]: l.split() for l in lines if l.startswith("  ") and len(l.split()) > 3}
        self.assertEqual(rows["iron1"][2:4], ["1.250", "1.250"])
        self.assertEqual(rows["bus"][2:4], ["1.250", "1.250"])
        self.assertEqual(checks, [])

    ONE_LANE = """
        ore   = MinerRow<n=18, resource=iron-ore>          @(8, 30, rot 2)
        coal  = Chest<requester, item=coal, rate=1/s>      @(1, 18)
        smelt = SmelterRow<n=26, recipe=iron-plate>        @(4, 18)
        bus   = Bus<belts=4, length=60, item=iron-plate, load=s2, tap=n28> @(0, 8)
        gears = AsmRow<n=5, recipe=iron-gear-wheel>        @(30, 0)
        gbox  = Chest<provider, limit=4>                   @(26, 1)
        gbox2 = Chest<provider, limit=4>                   @(26, 4)
        net ore_:  ore -> smelt
        net fuel:  coal -> smelt
        net iron1: smelt -> bus.load1
        net fe:    bus.tap1 -> gears
        net gear:  gears -> gbox, gbox2
    """

    def test_capacity_beyond_the_bus(self):
        # 26 furnaces make 8.125 plates/s, all on one lane of their row's belt: a lane carries
        # 7.5, so 7.5 get through, and the gears beyond the bus run short. One lane all the way:
        # the row's belt and its route, the load's first splitters, the tap's top ones, the
        # tap's route. The bus's belts have room: its staircases would spread what one belt
        # can't take, so none of them binds
        flat, lay, notes = laid(self.ONE_LANE)
        self.assertEqual(notes, [])
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {}, r.lines)
        rr = routed.solve(flat, r.layout, CAT)
        _lines, checks = routed.report(rr)
        cap = {c.where: c.msg for c in checks if c.code == "CAPACITY"}
        self.assertEqual(sorted(cap), ["net bus", "net fe", "net iron1"])
        self.assertIn("8.12/s required where its yellow lanes carry 7.50/s", cap["net iron1"])
        self.assertIn("gears/m4 runs at 0.00, 0.81 nominal", cap["net iron1"])
        self.assertIn("yellow splitters (a lane a side) carry 7.50/s", cap["net bus"])
        self.assertNotIn("bus/b", cap["net bus"])
        # red where it binds, and the plates come through; the bus's belts stay yellow
        from fkcore import tiers
        new, _tl, changed = tiers.assign(flat, r.layout, CAT, "minimize", ["yellow", "red"])
        self.assertEqual(sorted(k for k, (old, _new) in changed.items() if old == "splitter"),
                         ["bus/load1s0", "bus/load1s1", "bus/tap1s2", "bus/tap1s3"])
        self.assertFalse(any(k.startswith("bus/b") for k in changed))
        rr = routed.solve(flat, new, CAT)
        self.assertEqual([c for c in routed.report(rr, "t")[1] if c.code == "CAPACITY"], [])
        self.assertAlmostEqual(sum(rr.res.flow.get(("bus/tap1", lane), {}).get(PLATE, 0.0)
                                   for lane in ("L", "R")), 8.125)


if __name__ == "__main__":
    unittest.main()
