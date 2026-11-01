"""2.1 ribbons (PLAN-2.1 "Bus routing: ribbons"): several belts routed as one, side by side and in
order. ``width N`` above 2, ``bundle NAME: a, b`` and ``net each`` as a ribbon; the search
(``steiner.ribbon``): bus turns, every belt under a crossing together, belts that end one by one;
and the refusals. Ribbon tunnels: each belt under only what blocks its own line, and tunnels as
long as the tier allowed (``route_layout(ug=...)``) reaches, laid at the slowest tier that does."""
import os
import unittest

from fkcore import connect, expand, fkp, lang, route, tiers
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate, elaborate_file
from fkcore.steiner import Grid, ribbon

CAT = Catalog.load()
HERE = os.path.dirname(os.path.abspath(__file__))
NEST = os.path.join(HERE, "nest")

SRC = """
module Src size 4x4 {
  port o0 : out iron-plate @s0
  port o1 : out iron-plate @s1
  port o2 : out iron-plate @s2
  port o3 : out iron-plate @s3
  c0 = Chest<requester, item=iron-plate, rate=1/s> @(0, 0)
  c1 = Chest<requester, item=iron-plate, rate=1/s> @(1, 0)
  c2 = Chest<requester, item=iron-plate, rate=1/s> @(2, 0)
  c3 = Chest<requester, item=iron-plate, rate=1/s> @(3, 0)
  net a0: c0 -> o0
  net a1: c1 -> o1
  net a2: c2 -> o2
  net a3: c3 -> o3
}
"""
DST = """
module Dst size 4x4 {
  port i0 : in iron-plate @n0
  port i1 : in iron-plate @n1
  port i2 : in iron-plate @n2
  port i3 : in iron-plate @n3
  c0 = Chest<provider> @(0, 3)
  c1 = Chest<provider> @(1, 3)
  c2 = Chest<provider> @(2, 3)
  c3 = Chest<provider> @(3, 3)
  net b0: i0 -> c0
  net b1: i1 -> c1
  net b2: i2 -> c2
  net b3: i3 -> c3
}
"""
NETS = """
net p0: src.o0 -> dst.i0
net p1: src.o1 -> dst.i1
net p2: src.o2 -> dst.i2
net p3: src.o3 -> dst.i3
bundle plates: p0, p1, p2, p3
"""
P = ("p0", "p1", "p2", "p3")


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def routed(text, cross_x=None, bounds=None):
    """Route ``text``; ``cross_x``: another net's belt down column x over the whole box first."""
    flat = flat_of(text)
    lay, _notes = expand.expand_factory(flat, CAT)
    if cross_x is not None:
        for y in range(-2, 44):
            lay.add(fkp.Entity(f"~cross/b{y + 2}", "transport-belt", cross_x + 0.5, y + 0.5, 8,
                               {"net": "cross"}))
    r = route.route_layout(flat, lay, CAT, bounds=bounds or (-4, -4, 50, 50))
    rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
    return flat, r, rep


def of(r, net, name=None):
    return [e for e in r.layout.entities.values() if e.owner == f"~{net}"
            and (name is None or e.name == name)]


def at(e):
    return (int(e.x // 1), int(e.y // 1))


class SyntaxTest(unittest.TestCase):
    def test_wide_and_bundle_parse(self):
        f = lang.parse("net p width 8: a -> b\nbundle bb: p, q, r", "t.fk")
        self.assertEqual(f.body.nets[0].width, 8)
        b = f.body.bundles[0]
        self.assertEqual((b.name, b.nets), ("bb", ["p", "q", "r"]))

    def test_width_must_be_whole_belts(self):
        for w in ("3", "5", "7", "0", "2.5"):
            with self.subTest(width=w):
                with self.assertRaises(Exception) as cm:
                    lang.parse(f"net p width {w}: a -> b", "t.fk")
                self.assertIn("even number of lanes", str(cm.exception))

    def test_bundle_refusals(self):
        for text, said in (("bundle b: p", "two nets or more"),
                           ("bundle b: p, q, p", "named twice"),
                           ("net each p width 4: a[*].x -> b[*].y", "ribbon already")):
            with self.subTest(text=text):
                with self.assertRaises(Exception) as cm:
                    lang.parse(text, "t.fk")
                self.assertIn(said, str(cm.exception))


class ElaborateTest(unittest.TestCase):
    BASE = """
a = Chest<requester, item=iron-plate, rate=1/s> @(0, 0)
b = Chest<provider> @(10, 0)
c = Chest<requester, item=iron-plate, rate=1/s> @(0, 4)
d = Chest<provider> @(10, 4)
net p: a -> b
net q: c -> d
"""

    def test_a_bundle_lists_its_nets(self):
        flat = flat_of(self.BASE + "bundle pq: p, q\n")
        self.assertEqual(flat.bundles, {"pq": ["p", "q"]})

    def test_refused(self):
        for extra, said in (("bundle pq: p, z", "no net z"),
                            ("bundle p: p, q", "names a net"),
                            ("bundle pq: p, q\nbundle qp: q, p", "in a ribbon already"),
                            ("lanes p | q\nbundle pq: p, q", "shares a belt")):
            with self.subTest(extra=extra):
                with self.assertRaises(ElabError) as cm:
                    flat_of(self.BASE + extra)
                self.assertIn(said, str(cm.exception))

    def test_a_wide_net_short_of_drivers_is_a_check(self):
        flat = flat_of(self.BASE.replace("net q: c -> d\n", "") + "net w width 6: c -> d\n")
        lines = [str(c) for c in flat.checks if c.code == "width"]
        self.assertTrue(any("3 belts side by side, and it has 1 driver" in ln for ln in lines),
                        lines)


class SearchTest(unittest.TestCase):
    """steiner.ribbon on its own: a bus turn keeps the order, a crossing takes every belt."""

    def test_two_turns_and_a_crossing_keep_the_order(self):
        wall = {(10, y) for y in range(-5, 12)}
        grid = Grid(wall)
        grid.blocked = lambda t, occ=grid.occ: t in occ or not (-2 <= t[0] < 40 and -6 <= t[1] < 30)
        res = ribbon(grid, 4, [((0, 0, 1), 0.0)], fixed=[((23 - b, 20), 2) for b in range(4)])
        self.assertNotIn("fail", res)
        self.assertEqual(res["ends"], [("fixed",)] * 4)
        self.assertEqual((res["counts"]["turns"], res["counts"]["crossings"]), (1, 1))
        seen = set()
        for b, line in enumerate(res["lines"]):
            self.assertEqual(line[0][0], (0, b))            # east, belt b b tiles right (south)
            self.assertEqual(line[-1][0], (23 - b, 20))     # south: b tiles right is west
            ins = [t for t, k in line if k == "in"]
            outs = [t for t, k in line if k == "out"]
            self.assertEqual((ins, outs), ([(9, b)], [(14, b)]))   # side by side, one length
            for t, _k in line:
                self.assertNotIn(t, seen)
                seen.add(t)
        # the bus turn (right): belt 3, the inner one, turns first
        corner = {b: next(i for i, (t, _k) in enumerate(line) if t[0] == line[-1][0][0])
                  for b, line in enumerate(res["lines"])}
        xs = {b: res["lines"][b][corner[b]][0] for b in range(4)}
        self.assertEqual([xs[b][1] for b in range(4)], [0, 1, 2, 3])
        self.assertEqual([xs[b][0] for b in range(4)], [23, 22, 21, 20])


class BundleRouteTest(unittest.TestCase):
    def test_four_belts_two_turns_and_a_crossing(self):
        flat, r, rep = routed(SRC + DST + "src = Src @(2, 2)\ndst = Dst @(30, 30)\n" + NETS,
                              cross_x=16)
        self.assertEqual({n: r.failed.get(n) for n in P}, dict.fromkeys(P))
        self.assertEqual({n for n in P if rep.nets[n].status != "connected"}, set())
        self.assertEqual(rep.leaks, [])
        line = next(ln for ln in r.lines if ln.startswith("ribbon"))
        self.assertIn("ribbon    plates: 4 belts side by side", line)
        self.assertIn("2 bus turns, 1 crossing (4 belts under: ", line)
        # every belt under the crossing belt together: four entrances in one column, four exits
        # in another, each pair the same length, in the belts' order
        ins = {n: [at(e) for e in of(r, n, "underground-belt") if e.attrs.get("ug") == "in"]
               for n in P}
        outs = {n: [at(e) for e in of(r, n, "underground-belt") if e.attrs.get("ug") == "out"]
                for n in P}
        self.assertTrue(all(len(ins[n]) == len(outs[n]) == 1 for n in P), (ins, outs))
        self.assertEqual(len({ins[n][0][0] for n in P}), 1)
        self.assertEqual(len({outs[n][0][0] for n in P}), 1)
        self.assertTrue(ins["p0"][0][0] < 16 < outs["p0"][0][0])
        ys = [ins[n][0][1] for n in P]
        self.assertEqual(sorted(ys), list(range(min(ys), min(ys) + 4)))
        self.assertEqual(ys, sorted(ys, reverse=True))       # p0 outermost, in order
        self.assertEqual([outs[n][0][1] for n in P], ys)

    def test_belts_end_one_by_one(self):
        text = SRC + """
src = Src @(2, 2)
k3 = Chest<provider> @(10, 14)
k2 = Chest<provider> @(10, 20)
k1 = Chest<provider> @(10, 26)
k0 = Chest<provider> @(10, 32)
net p0: src.o0 -> k0
net p1: src.o1 -> k1
net p2: src.o2 -> k2
net p3: src.o3 -> k3
bundle plates: p0, p1, p2, p3
"""
        flat, r, rep = routed(text)
        self.assertEqual({n for n in P if rep.nets[n].status != "connected"}, set())
        self.assertEqual(rep.leaks, [])
        line = next(ln for ln in r.lines if ln.startswith("ribbon"))
        self.assertIn("0 belts end where its consumer's belt starts, 4 on in a belt of its own",
                      line)
        # each leaves where its chest is, the outer one first: the ribbon's lengths differ
        body = {n: int(r.lines[[ln.split()[1] for ln in r.lines].index(f"{n}:")]
                       .split("belts side by side): ")[1].split(" belts")[0]) for n in P}
        self.assertEqual(len(set(body.values())), 4, body)
        self.assertEqual(sorted(P, key=body.get), ["p3", "p2", "p1", "p0"])
        # the belts still in the ribbon keep their offsets: where p3 leaves, p0..p2 run on in
        # the same columns they ran in before
        cols = {n: {at(e)[0] for e in of(r, n, "transport-belt") if 8 <= at(e)[1] <= 13}
                for n in P}
        self.assertEqual([sorted(cols[n]) for n in P], [[2], [3], [4], [5]])

    def test_running_different_ways_is_refused(self):
        text = SRC + DST.replace("Dst", "Dst2") + """
src = Src @(20, 20)
dst = Dst2 @(20, 34)
far = Chest<provider> @(2, 2)
net p0: src.o0 -> dst.i0
net p1: src.o1 -> dst.i1
net p2: src.o2 -> dst.i2
net p3: src.o3 -> far
bundle plates: p0, p1, p2, p3
"""
        _flat, r, _rep = routed(text)
        for n in P:
            self.assertIn("its nets run different ways", r.failed.get(n, ""))
            self.assertEqual(of(r, n), [])

    def test_no_way_wide_enough_is_unrouted_not_loose(self):
        # two thick walls leave a gap of three tiles: one belt gets through, four side by side
        # don't, and a ribbon is never split into loose belts
        text = SRC + DST + """
module Wall size 8x30 {
  c = Chest<provider> @(0, 0)
}
src = Src @(2, 2)
dst = Dst @(2, 40)
wl = Wall @(-8, 10)
wr = Wall @(3, 10)
""" + NETS
        flat = flat_of(text)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT, bounds=(-8, 0, 11, 46))
        for n in P:
            self.assertIn("ribbon plates (4 belts)", r.failed.get(n, ""))
            self.assertEqual(of(r, n), [])
        self.assertFalse(any(ln.startswith("ribbon") for ln in r.lines))


class WideNetTest(unittest.TestCase):
    TEXT = """
d0 = Chest<requester, item=iron-plate, rate=5/s> @(2, 2)
d1 = Chest<requester, item=iron-plate, rate=5/s> @(6, 2)
d2 = Chest<requester, item=iron-plate, rate=5/s> @(10, 2)
d3 = Chest<requester, item=iron-plate, rate=5/s> @(14, 2)
k0 = Chest<provider> @(30, 30)
k1 = Chest<provider> @(36, 30)
net plates width 4: d0, d1, d2, d3 -> k0, k1
"""

    def test_two_belts_drivers_dealt_out(self):
        _flat, r, rep = routed(self.TEXT)
        self.assertNotIn("plates", r.failed)
        self.assertEqual(rep.nets["plates"].status, "connected")
        self.assertEqual(rep.leaks, [])
        line = next(ln for ln in r.lines if ln.startswith("ribbon"))
        self.assertIn("2 belts side by side (net plates width 4, its drivers dealt out)", line)
        # each driver reaches one belt's consumer, not both: the drivers were dealt out
        g = connect.graph(r.layout, CAT)
        sinks = {"k0/c0", "k1/c0"}
        reach = {d: g.reach({f"{d}/c0"}, "plates") & sinks for d in ("d0", "d1", "d2", "d3")}
        self.assertTrue(all(len(v) == 1 for v in reach.values()), reach)
        self.assertEqual(sorted(len([d for d in reach if reach[d] == {k}]) for k in sinks),
                         [2, 2])

    def test_too_few_consumers_is_refused(self):
        _flat, r, _rep = routed(self.TEXT.replace("k0, k1", "k0").replace("width 4", "width 6"))
        self.assertIn("is 3 belts, and 1 consumer is placed: each belt needs one of its own",
                      r.failed.get("plates", ""))

    def test_more_than_its_belts_carry_is_refused(self):
        _flat, r, _rep = routed(self.TEXT.replace("rate=5/s", "rate=20/s"))
        self.assertIn("more than one belt's two lanes", r.failed.get("plates", ""))


class NetEachTest(unittest.TestCase):
    def test_the_smelter_bus_is_one_ribbon(self):
        flat = elaborate_file(os.path.join(NEST, "bus-ribbon.fk"), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        nets = [f"plates_{k}" for k in range(8)]
        self.assertEqual({n: r.failed.get(n) for n in nets}, dict.fromkeys(nets))
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
        self.assertEqual({n for n in nets if rep.nets[n].status != "connected"}, set())
        self.assertEqual(rep.leaks, [])
        line = next(ln for ln in r.lines if ln.startswith("ribbon"))
        self.assertIn("ribbon    plates: 8 belts side by side", line)
        self.assertIn("2 bus turns", line)
        # into the row of chests in order: belt k ends on port k
        ends = {}
        for k, n in enumerate(nets):
            last = max((e for e in of(r, n, "transport-belt")), key=lambda e: e.y)
            ends[k] = at(last)
        self.assertEqual([ends[k][0] for k in range(8)], list(range(100, 108)))


if __name__ == "__main__":
    unittest.main()


def ends8(n=8):
    """Src8 (n requesters, ports south) and Dst8 (n providers, ports north), n belts apart."""
    src = [f"module Src8 size {n}x4 {{"] + [f"  port o{k} : out iron-plate @s{k}" for k in range(n)] \
        + [f"  c{k} = Chest<requester, item=iron-plate, rate=1/s> @({k}, 0)" for k in range(n)] \
        + [f"  net a{k}: c{k} -> o{k}" for k in range(n)] + ["}"]
    dst = [f"module Dst8 size {n}x4 {{"] + [f"  port i{k} : in iron-plate @n{k}" for k in range(n)] \
        + [f"  c{k} = Chest<provider> @({k}, 3)" for k in range(n)] \
        + [f"  net b{k}: i{k} -> c{k}" for k in range(n)] + ["}"]
    nets = [f"net q{k}: src.o{k} -> dst.i{k}" for k in range(n)] \
        + ["bundle plates: " + ", ".join(f"q{k}" for k in range(n))]
    return "\n".join(src + dst + nets) + "\n"


Q = tuple(f"q{k}" for k in range(8))


def wall_across(rows, y=12):
    """A module as wide as the box, ``rows`` tall at ``y``: no way round it, only under."""
    return (f"module Wall size 30x{rows} {{\n  c = Chest<provider> @(0, 0)\n}}\n"
            f"wall = Wall @(-6, {y})\n")


class TunnelTest(unittest.TestCase):
    """2.1 ribbon tunnels: each belt under on its own, and a reach that follows the tier."""

    def route8(self, rows, ug):
        text = ends8() + "src = Src8 @(2, 2)\ndst = Dst8 @(2, 30)\n" + wall_across(rows)
        flat = flat_of(text)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT, bounds=(-6, -4, 24, 40), ug=ug)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
        return flat, r, rep

    def ugs(self, r, net):
        return [e for e in r.layout.entities.values() if e.owner == f"~{net}"
                and CAT.has_entity(e.name) and CAT.kind(e.name) == "underground-belt"]

    def test_eight_belts_cross_six_rows_on_red(self):
        # six rows of wall: entrance above it, exit below, 7 tiles apart, past yellow's 5
        flat, r, rep = self.route8(6, "red")
        self.assertEqual({n: r.failed.get(n) for n in Q}, dict.fromkeys(Q))
        self.assertEqual({n for n in Q if rep.nets[n].status != "connected"}, set())
        self.assertEqual(rep.leaks, [])
        for n in Q:
            ends = sorted(self.ugs(r, n), key=lambda e: e.y)
            self.assertEqual([e.name for e in ends], ["fast-underground-belt"] * 2, n)
            self.assertEqual([at(e)[1] for e in ends], [11, 18], n)
            self.assertEqual([e.attrs.get("ug") for e in ends], ["in", "out"])
        cols = [at(self.ugs(r, n)[0])[0] for n in Q]
        self.assertEqual(sorted(cols), list(range(2, 10)))
        line = next(ln for ln in r.lines if ln.startswith("ribbon"))
        self.assertIn("1 crossing (8 belts under: ", line)
        self.assertIn("(7 tiles red)", line)
        # the tier pass never gives such a tunnel an underground that falls short
        for mode, down in (("yellow", False), ("minimize", True)):
            new, _lines, _changed = tiers.assign(flat, r.layout, CAT, mode=mode, downgrade=down)
            names = {e.name for k, e in new.entities.items() if k.startswith("~q")
                     and CAT.kind(e.name) == "underground-belt"}
            self.assertEqual(names, {"fast-underground-belt"}, mode)

    def test_on_yellow_six_rows_is_unrouted(self):
        _flat, r, _rep = self.route8(6, None)
        for n in Q:
            self.assertIn("ribbon plates (8 belts)", r.failed.get(n, ""))
            self.assertEqual(of(r, n), [])

    def test_eight_rows_fit_blue_not_yellow_or_red(self):
        for ug in ("yellow", "red"):
            _flat, r, _rep = self.route8(8, ug)
            self.assertTrue(all(n in r.failed for n in Q), ug)
        _flat, r, rep = self.route8(8, "blue")
        self.assertEqual({n for n in Q if rep.nets[n].status != "connected"}, set())
        for n in Q:
            ends = sorted(self.ugs(r, n), key=lambda e: e.y)
            self.assertEqual([e.name for e in ends], ["express-underground-belt"] * 2, n)
            self.assertEqual([at(e)[1] for e in ends], [11, 20], n)

    def test_only_the_blocked_belts_go_under(self):
        # a rock under the third and fourth columns: those two belts go under it, the others
        # run on over the surface, and every belt keeps its column
        text = SRC + DST + "src = Src @(2, 2)\ndst = Dst @(2, 30)\n" + NETS
        flat = flat_of(text)
        lay, _notes = expand.expand_factory(flat, CAT)
        for i, (x, y) in enumerate([(4, 15), (5, 15), (4, 16), (5, 16)]):
            lay.add(fkp.Entity(f"rock/{i}", "stone-wall", x + 0.5, y + 0.5, 0, {}))
        r = route.route_layout(flat, lay, CAT, bounds=(0, -4, 8, 40))
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
        self.assertEqual({n for n in P if rep.nets[n].status != "connected"}, set())
        under = {n for n in P if of(r, n, "underground-belt")}
        cols = {n: {at(e)[0] for e in of(r, n)} for n in P}
        self.assertEqual({n for n in P if cols[n] & {4, 5}}, under)
        self.assertEqual(len(under), 2)
        for n in P:
            self.assertEqual(len(cols[n]), 1, cols)            # straight down its own column
            if n in under:
                ys = sorted(at(e)[1] for e in of(r, n, "underground-belt"))
                self.assertEqual(ys[0], 14)                     # just before the rock
                self.assertTrue(17 <= ys[1] <= 19, ys)          # past it, within yellow's 5
        line = next(ln for ln in r.lines if ln.startswith("ribbon"))
        self.assertIn("1 crossing (2 belts under: ", line)

    def test_search_tunnels_each_belt_on_its_own(self):
        # steiner.ribbon alone: three belts east, a block on belt 1's line only, another on
        # belt 2's two tiles later; each belt goes under its own, belt 0 never
        grid = Grid({(5, 1), (8, 2), (9, 2)})
        grid.blocked = lambda t, occ=grid.occ: t in occ or not (0 <= t[0] < 20 and 0 <= t[1] < 3)
        res = ribbon(grid, 3, [((0, 0, 1), 0.0)], fixed=[((15, b), 1) for b in range(3)])
        self.assertNotIn("fail", res)
        kinds = [[k for _t, k in line] for line in res["lines"]]
        self.assertNotIn("in", kinds[0])
        ins = [[t for t, k in line if k == "in"] for line in res["lines"]]
        outs = [[t for t, k in line if k == "out"] for line in res["lines"]]
        self.assertEqual(ins[1], [(4, 1)])
        self.assertEqual(ins[2], [(7, 2)])
        self.assertTrue(outs[1][0][0] >= 6 and outs[2][0][0] >= 10, outs)
        self.assertEqual(res["counts"]["under"], 2)

    def test_route_ug_option(self):
        from fkcore import avail, flow
        saved = avail.snapshot()
        avail.install(None)
        try:
            self.assertEqual(flow._ribbon_ug("red"), ("red", None))
            self.assertEqual(flow._ribbon_ug("any"), ("yellow", None))    # nothing read: yellow
            with self.assertRaises(flow.FlowError):
                flow._ribbon_ug("purple")
        finally:
            avail.install(saved.sup, saved.when, saved.tick)
