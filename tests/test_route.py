import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import connect, expand, fkp, flow, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, elaborate_file

CAT = Catalog.load()
REDGREEN = os.path.join(os.path.dirname(__file__), "..", "games", "redgreen", "main.fk")
SPM10 = os.path.join(os.path.dirname(__file__), "..", "games", "spm10", "main.fk")
LAB_KXM = os.path.join(os.path.dirname(__file__), "..", "games", "lab-kxm")

BASE = """
ore   = MinerRow<n=2, resource=iron-ore>  @(14, 0, rot 2)
coal  = MinerRow<n=1, resource=coal>      @(24, 0, rot 2)
smelt = SmelterRow<n=2, recipe=iron-plate> @(6, 12)
pipes = AsmRow<n=1, recipe=pipe>           @(6, 24)
net ore_: ore -> smelt
net fuel: coal -> smelt
"""


TWO_SMELTERS = """
ore    = MinerRow<n=2, resource=iron-ore>   @(14, 0, rot 2)
coal   = MinerRow<n=1, resource=coal>       @(24, 0, rot 2)
smelt  = SmelterRow<n=2, recipe=iron-plate> @(6, 12)
smelt2 = SmelterRow<n=2, recipe=iron-plate> @(16, 12)
pipes  = AsmRow<n=1, recipe=pipe>           @(6, 24)
net ore_: ore -> smelt, smelt2
net fuel: coal -> smelt, smelt2
"""


def build(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, notes = expand.expand_factory(flat, CAT)
    assert fkp.invariants(lay, CAT) == [], fkp.invariants(lay, CAT)
    return flat, lay


def judged(flat, r):
    rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
    return {n: x.status for n, x in rep.nets.items()}, rep


def connected(test, flat, r):
    """Every net routed and connected, no LEAK, no check line at all, a well-formed layout."""
    test.assertEqual(r.failed, {}, r.lines)
    test.assertEqual(fkp.invariants(r.layout, CAT, nets=flat.nets), [])
    status, rep = judged(flat, r)
    test.assertEqual(set(status.values()), {"connected"}, rep.lines())
    test.assertEqual(rep.leaks, [])
    test.assertEqual(rep.checks, [])
    return rep


def carriers(r, net):
    return [e for k, e in sorted(r.layout.entities.items()) if k.startswith(f"~{net}/")]


class SmallTest(unittest.TestCase):
    def test_paths(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertEqual(sorted(r.routed), ["fuel", "ore_", "plate"])
        self.assertEqual(fkp.invariants(r.layout, CAT), [])
        status, rep = judged(flat, r)
        self.assertEqual(set(status.values()), {"connected"}, rep.lines())
        self.assertEqual(rep.leaks, [])
        # every route carrier is keyed under its net and carries it
        for key, e in r.layout.entities.items():
            if key.startswith("~"):
                self.assertEqual(e.net, e.owner[1:], key)

    def test_a_split_and_a_merge(self):
        # ore and fuel feed two smelter rows (1 -> 2: a splitter); the two rows feed one pipe row
        # (2 -> 1: grown from the consumer and laid reversed, so its splitter is a merge)
        flat, lay = build(TWO_SMELTERS + "net plate: smelt, smelt2 -> pipes\n")
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {}, r.lines)
        for net in ("ore_", "fuel", "plate"):
            names = [e.name for k, e in r.layout.entities.items() if k.startswith(f"~{net}/")]
            self.assertEqual(names.count("splitter"), 1, net)
        status, rep = judged(flat, r)
        self.assertEqual(set(status.values()), {"connected"}, rep.lines())
        self.assertEqual(rep.leaks, [])

    def test_several_drivers_and_consumers_merge_then_split(self):
        # was "reported, not routed": now every driver merges into one trunk, which splits to
        # every consumer (a hub)
        flat, lay = build(TWO_SMELTERS + """
            sticks = AsmRow<n=1, recipe=iron-stick> @(16, 24)
            net plate: smelt, smelt2 -> pipes, sticks
        """)
        r = route.route_layout(flat, lay, CAT)
        line = next(l for l in r.lines if " plate:" in l)
        self.assertTrue(line.startswith("routed    plate: 2 -> 2,"), line)
        self.assertIn("1 merges, 1 splitters", line)
        rep = connected(self, flat, r)
        self.assertEqual((rep.nets["plate"].pairs, rep.nets["plate"].reached), (8, 8))

    def test_an_unreachable_net_fails_with_a_reason(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        r = route.route_layout(flat, lay, CAT, bounds=(0, 0, 40, 23))   # pipes' head is outside
        self.assertIn("plate", r.failed)
        self.assertTrue(any(l.startswith("FAILED    plate:") for l in r.lines))
        self.assertEqual(sorted(r.routed), ["fuel", "ore_"])

    def test_laid_nets_are_kept(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        first = route.route_layout(flat, lay, CAT)
        again = route.route_layout(flat, first.layout, CAT)
        self.assertEqual(again.routed, [])
        self.assertEqual(sorted(again.kept), ["fuel", "ore_", "plate"])
        self.assertEqual(fkp.dumps(again.layout), fkp.dumps(first.layout))

    def test_blocked_ground_is_avoided(self):
        # terrain (water, cliffs) comes in as blocked tiles: the route goes round them
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        first = route.route_layout(flat, lay, CAT)
        belts = sorted(k for k, e in first.layout.entities.items()
                       if k.startswith("~plate/b") and e.name == "transport-belt")
        e = first.layout.entities[belts[len(belts) // 2]]
        tile = (int(e.x), int(e.y))
        r = route.route_layout(flat, lay, CAT, blocked=[tile])
        self.assertEqual(r.failed, {}, r.lines)
        used = set()
        for k, x in r.layout.entities.items():
            if k.startswith("~"):
                used |= fkp.tiles_of(CAT, x)
        self.assertNotIn(tile, used)
        status, rep = judged(flat, r)
        self.assertEqual(set(status.values()), {"connected"}, rep.lines())

    def test_a_fluid_net_goes_to_the_fluid_plug_in(self):
        # pipes are not belts: a fluid net is never laid as a belt route by this router
        flat, lay = build(BASE + """
            water = OffshorePump        @(30, 12)
            chem  = ChemPlant<recipe=sulfur> @(30, 20)
            net plate: smelt -> pipes
            net w: water -> chem
        """)
        self.assertEqual(route.fluid_nets(flat, CAT), {"w"})
        r = route.route_layout(flat, lay, CAT)
        self.assertIn("plate", r.routed)
        carriers = {e.name for k, e in r.layout.entities.items() if k.startswith("~w/")}
        self.assertLessEqual(carriers, {"pipe", "pipe-to-ground"})
        if route._fluid_plugin() is None:                  # until fkcore.fluid_route is built
            line = next(l for l in r.lines if " w:" in l)
            self.assertTrue(line.startswith("skipped   w: a fluid net"), line)

    def test_deterministic(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        a = route.route_layout(flat, lay, CAT)
        b = route.route_layout(flat, lay, CAT)
        self.assertEqual(fkp.dumps(a.layout), fkp.dumps(b.layout))


class SeveralDriversTest(unittest.TestCase):
    """k -> m nets (CORE: a route joins every driver to every consumer): merge, then split."""

    def test_three_drivers_two_consumers(self):
        flat, lay = build("""
            ore    = MinerRow<n=2, resource=iron-ore>   @(14, 0, rot 2)
            coal   = MinerRow<n=1, resource=coal>       @(24, 0, rot 2)
            smelt  = SmelterRow<n=2, recipe=iron-plate> @(6, 12)
            smelt2 = SmelterRow<n=2, recipe=iron-plate> @(16, 12)
            smelt3 = SmelterRow<n=2, recipe=iron-plate> @(26, 12)
            pipes  = AsmRow<n=1, recipe=pipe>           @(6, 24)
            sticks = AsmRow<n=1, recipe=iron-stick>     @(16, 24)
            net ore_:  ore -> smelt, smelt2, smelt3
            net fuel:  coal -> smelt, smelt2, smelt3
            net plate: smelt, smelt2, smelt3 -> pipes, sticks
        """)
        r = route.route_layout(flat, lay, CAT)
        line = next(l for l in r.lines if " plate:" in l)
        self.assertTrue(line.startswith("routed    plate: 3 -> 2,"), line)
        self.assertIn("2 merges, 1 splitters", line)
        rep = connected(self, flat, r)
        self.assertEqual((rep.nets["plate"].pairs, rep.nets["plate"].reached), (12, 12))
        self.assertEqual(sum(e.name == "splitter" for e in carriers(r, "plate")), 3)

    def test_a_sushi_output_into_one_chest(self):
        # the mall's shape (CORE-V1 §11, mall.* -> mall_chest): every product into one chest
        flat, lay = build("""
            gears = Assembler<recipe=iron-gear-wheel> @(2, 2)
            pipes = Assembler<recipe=pipe>            @(10, 2)
            stick = Assembler<recipe=iron-stick>      @(18, 2)
            box   = Chest<provider>                   @(10, 14)
            net out: gears, pipes, stick -> box
        """)
        self.assertEqual(flat.nets["out"].items, ["iron-gear-wheel", "pipe", "iron-stick"])
        r = route.route_layout(flat, lay, CAT)
        line = next(l for l in r.lines if " out:" in l)
        self.assertTrue(line.startswith("routed    out: 3 -> 1,"), line)
        rep = connected(self, flat, r)
        self.assertEqual(rep.nets["out"].reached, 3)
        # one inserter per machine; fast ones (Rory's rule)
        hands = [e.name for e in carriers(r, "out") if CAT.kind(e.name) == "inserter"]
        self.assertEqual(hands, ["fast-inserter"] * 4)

    def test_machine_drivers(self):
        # a requester chest into two rows was a crash (one machine driver, several consumers);
        # chest -> chest went unrouted; chest -> assembler beside it is one inserter
        two_rows = build("""
            inbox = Chest<requester, item=iron-plate>   @(2, 8)
            gears = AsmRow<n=1, recipe=iron-gear-wheel> @(8, 2)
            pipes = AsmRow<n=1, recipe=pipe>            @(8, 12)
            net plates: inbox -> gears, pipes
        """)
        chest = build("""
            inbox = Chest<requester, item=iron-plate> @(2, 2)
            box   = Chest<provider>                   @(12, 9)
            net p: inbox -> box
        """)
        direct = build("""
            inbox = Chest<requester, item=iron-plate> @(2, 2)
            gear  = Assembler<recipe=iron-gear-wheel> @(4, 1)
            net plates: inbox -> gear
        """)
        for flat, lay in (two_rows, chest, direct):
            connected(self, flat, route.route_layout(flat, lay, CAT))
        r = route.route_layout(*direct, CAT)
        self.assertEqual([(e.name, e.x, e.y, e.dir) for e in carriers(r, "plates")],
                         [("fast-inserter", 3.5, 2.5, 12)])       # picks from the chest, west
        self.assertIn("1 inserter (direct insertion)", r.lines[0])

    def test_a_machine_hands_to_every_neighbour_by_an_inserter(self):
        # 1.3 (Rory, 2026-10-20: a mall placed with care): one machine driver, its consumers one
        # tile away each take from it by an inserter of their own; only the far one gets a belt
        near = build("""
            yb  = Assembler<recipe=transport-belt>        @(4, 4)
            yu  = Assembler<recipe=underground-belt>      @(4, 0)
            ys  = Assembler<recipe=splitter>              @(8, 4)
            rb  = Assembler<recipe=fast-transport-belt>   @(4, 8)
            ybc = Chest<provider, limit=2>                @(2, 5)
            net ybo: yb -> yu, ys, rb, ybc
        """)
        r = route.route_layout(*near, CAT)
        connected(self, near[0], r)
        self.assertEqual(sorted(e.name for e in carriers(r, "ybo")), ["fast-inserter"] * 4)
        self.assertIn("4 inserters (direct insertion)", r.lines[0])
        far = build("""
            yb  = Assembler<recipe=transport-belt>        @(4, 4)
            yu  = Assembler<recipe=underground-belt>      @(4, 0)
            far = Assembler<recipe=underground-belt>      @(14, 12)
            net ybo: yb -> yu, far
        """)
        r = route.route_layout(*far, CAT)
        connected(self, far[0], r)
        names = [e.name for e in carriers(r, "ybo")]
        self.assertIn("transport-belt", names)
        self.assertIn("1 inserter (direct insertion), then", r.lines[0])

    def test_the_early_mall_links_its_products_by_inserters(self):
        # agent/docs/examples/early-mall.fk (Rory, 2026-10-20): every product link one inserter,
        # belts only for the iron, copper and circuit feeds
        path = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples",
                            "early-mall.fk")
        flat = elaborate_file(path, CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        direct = {l.split()[1].rstrip(":") for l in r.lines if l.endswith("(direct insertion)")}
        products = {"ybo", "yuo", "yso", "rbo", "ruo", "rso", "inso", "finso", "linso", "asmo",
                    "drillo", "pipeo", "ptgo"}
        self.assertEqual(products - direct, set())
        belts = sum(1 for k, e in r.layout.entities.items()
                    if k.startswith("~") and e.name == "transport-belt")
        self.assertLessEqual(belts, 100)

    def test_two_sushi_chests_into_two_chests(self):
        # the lab game's shape (games/lab-kxm): each consumer must get every driver's item
        flat, lay = build("""
            a = Chest<requester, item=iron-plate>   @(2, 2)
            b = Chest<requester, item=copper-plate> @(2, 10)
            x = Chest<provider> @(16, 3)
            y = Chest<provider> @(16, 11)
            net mix: a, b -> x, y
        """)
        rep = connected(self, flat, route.route_layout(flat, lay, CAT))
        self.assertEqual((rep.nets["mix"].pairs, rep.nets["mix"].reached), (4, 4))

    def test_deterministic(self):
        text = TWO_SMELTERS + """
            sticks = AsmRow<n=1, recipe=iron-stick> @(16, 24)
            net plate: smelt, smelt2 -> pipes, sticks
        """
        a = route.route_layout(*build(text), CAT)
        b = route.route_layout(*build(text), CAT)
        self.assertEqual(fkp.dumps(a.layout), fkp.dumps(b.layout))


class Spm10Test(unittest.TestCase):
    """games/spm10/main.fk has no placement: the instances on its iron net and the mall's sushi
    output are shelf-packed here (hints set on the netlist), then the router lays every net it
    can reach and connect judges the two."""

    @classmethod
    def setUpClass(cls):
        flat = elaborate_file(SPM10, CAT)
        mine = set()
        for net in ("iron_plate", "mall_out"):
            n = flat.nets[net]
            mine |= {flat.machines[k].inst for k, _i in n.drivers + n.consumers}
        for path, inst in flat.insts.items():
            inst.hints["at"] = (0, 0, 0)
        sizes = {p: expand.fragment_of(flat, p, CAT)[0].size for p in sorted(mine)}
        x, y, row = 5, 5, 0
        for p in sorted(mine, key=lambda p: (sizes[p][0] <= 3, p)):    # rows first, then cells
            w, h = sizes[p]
            if x + w + 5 > 140:
                x, y, row = 5, y + row + 5, 0
            flat.insts[p].hints["at"] = (x, y, 0)
            x, row = x + w + (5 if w > 3 else 3), max(row, h)
        for path, inst in flat.insts.items():
            if path not in mine and inst.module is None:
                del inst.hints["at"]
        lay, _notes = expand.expand_factory(flat, CAT)
        cls.flat = flat
        cls.r = route.route_layout(flat, lay, CAT)
        cls.rep = connect.connect(cls.r.layout, CAT, connect.endpoints(flat))

    def test_the_iron_net_and_the_mall_output_connect(self):
        lines = {l.split(":")[0].split()[-1]: l for l in self.r.lines}
        self.assertTrue(lines["iron_plate"].startswith("routed    iron_plate: 1 -> 26,"),
                        lines["iron_plate"])
        self.assertTrue(lines["mall_out"].startswith("routed    mall_out: 20 -> 1,"),
                        lines["mall_out"])
        iron, out = self.rep.nets["iron_plate"], self.rep.nets["mall_out"]
        self.assertEqual((iron.status, iron.reached, iron.pairs), ("connected", 608, 608))
        self.assertEqual((out.status, out.reached, out.pairs), ("connected", 20, 20))
        self.assertEqual(self.rep.leaks, [])
        self.assertEqual(fkp.invariants(self.r.layout, CAT, nets=self.flat.nets), [])
        # every net the router laid connects its placed ends; the open ones lack unplaced ends
        for name in self.r.routed:
            net = self.rep.nets[name]
            self.assertTrue(net.connected or net.missing or any(
                d not in self.r.layout.entities or c not in self.r.layout.entities
                for d, c in net.unreached), (name, net.unreached[:3]))


class LabKxmTest(unittest.TestCase):
    """games/lab-kxm, the k -> m game applied on the lab surface: its flow on paper (no game link)
    writes the committed layout, and the one sushi net connects every driver to every chest."""

    def test_the_flow_on_paper(self):
        with tempfile.TemporaryDirectory(prefix="fkkxm-") as d:
            for name in ("kxm.fk", "lab.surface", "lab.build.fkb"):
                shutil.copy(os.path.join(LAB_KXM, name), d)
            with mock.patch.dict(os.environ, {"FK_LINK": "off"}):
                code, ctx = flow.run(os.path.join(d, "lab.build.fkb"), cat=CAT,
                                     echo=lambda _l: None)
            self.assertEqual(code, 0, ctx.log)
            for name in ("kxm.fkp", "lab.fkp"):
                with open(os.path.join(d, name), encoding="utf-8") as a, \
                        open(os.path.join(LAB_KXM, name), encoding="utf-8") as b:
                    self.assertEqual(a.read(), b.read(), name)
        rep = connect.connect(ctx.layouts["kxm"], CAT, connect.endpoints(ctx.flats["kxm"]))
        mix = rep.nets["mix"]
        self.assertEqual((mix.status, mix.reached, mix.pairs), ("connected", 6, 6))
        self.assertEqual(rep.leaks, [])
        self.assertEqual(sorted(ctx.flats["kxm"].nets["mix"].items),
                         ["copper-ore", "iron-gear-wheel", "iron-ore"])


class RedgreenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat = elaborate_file(REDGREEN, CAT)
        lay, cls.notes = expand.expand_factory(cls.flat, CAT)
        cls.r = route.route_layout(cls.flat, lay, CAT)
        cls.rep = connect.connect(cls.r.layout, CAT, connect.endpoints(cls.flat))

    def test_every_net_routes_and_connects_without_leak(self):
        self.assertEqual(self.notes, [])
        self.assertEqual(self.r.failed, {})
        self.assertEqual(len(self.r.routed), 12)
        self.assertEqual(fkp.invariants(self.r.layout, CAT, nets=self.flat.nets), [])
        self.assertEqual({x.status for x in self.rep.nets.values()}, {"connected"})
        self.assertEqual(self.rep.leaks, [])
        self.assertEqual(self.rep.checks, [])          # no UNROUTED, OPEN, LEAK or UG_SIDELOAD

    def test_counts(self):
        routes = [e for k, e in self.r.layout.entities.items() if k.startswith("~")]
        self.assertEqual(len(self.r.layout.entities), 566 + len(routes))
        print(f"\nredgreen routed: {len(routes)} route carriers "
              f"({sum(e.name == 'transport-belt' for e in routes)} belts, "
              f"{sum(e.name == 'underground-belt' for e in routes)} underground ends, "
              f"{sum(e.name == 'splitter' for e in routes)} splitters), "
              f"{self.r.passes} passes; {self.rep.summary()}")


if __name__ == "__main__":
    unittest.main()
