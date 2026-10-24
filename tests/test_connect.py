"""Connectivity (CORE-V1.md §9): the carrier graph, per-net connected yes/no, and LEAK lines.

Each case is a small hand-built layout in .fkp text. Directions follow the .fkp: N E S W; an
inserter faces the side it picks from (v4 convention), a long-handed one reaches two tiles; both
ends of an underground face the flow.
"""
import os
import unittest

from fkcore import compose, expand, fkp
from fkcore.catalog import Catalog
from fkcore.connect import connect, endpoints, graph
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "spm10")


def L(text, name="t"):
    """A factory layout from ``e`` lines (the header is added)."""
    return fkp.loads(f"fkp 1 factory {name}\n" + "\n".join(l.strip() for l in text.splitlines()))


def succ(g, key):
    return {(k, via) for k, via in g.succ.get(key, ())}


def leaks(rep):
    return [str(c) for c in rep.checks if c.code == "LEAK"]


class BeltTest(unittest.TestCase):
    def test_straight_and_curve(self):
        g = graph(L("""
            e a/b0 transport-belt 0.5,0.5 E net=a
            e a/b1 transport-belt 1.5,0.5 E net=a
            e a/b2 transport-belt 2.5,0.5 S net=a
            e a/b3 transport-belt 2.5,1.5 S net=a"""), CAT)
        self.assertEqual(succ(g, "a/b0"), {("a/b1", "belt")})
        self.assertEqual(succ(g, "a/b1"), {("a/b2", "curve")})      # its only input, from the side
        self.assertEqual(succ(g, "a/b2"), {("a/b3", "belt")})
        self.assertEqual(succ(g, "a/b3"), set())                     # points at nothing
        self.assertIn("a/b3", g.reach({"a/b0"}, "a"))

    def test_head_on_belts_do_not_connect(self):
        g = graph(L("""
            e a/b0 transport-belt 0.5,0.5 E net=a
            e a/b1 transport-belt 1.5,0.5 W net=a"""), CAT)
        self.assertEqual(succ(g, "a/b0"), set())
        self.assertEqual(succ(g, "a/b1"), set())

    def test_side_load(self):
        g = graph(L("""
            e a/b0 transport-belt 0.5,1.5 E net=a
            e a/b1 transport-belt 1.5,1.5 E net=a
            e a/b2 transport-belt 2.5,1.5 E net=a
            e a/s0 transport-belt 1.5,0.5 S net=a"""), CAT)
        self.assertEqual(succ(g, "a/s0"), {("a/b1", "sideload")})   # b1 is fed from behind too
        self.assertEqual(succ(g, "a/b0"), {("a/b1", "belt")})
        self.assertEqual(g.reach({"a/s0"}, "a"), {"a/s0", "a/b1", "a/b2"})

    def test_side_load_onto_an_underground(self):
        g = graph(L("""
            e a/s0 transport-belt 0.5,0.5 E net=a
            e a/u0 underground-belt 1.5,0.5 S net=a ug=in
            e a/s1 transport-belt 3.5,0.5 W net=a
            e a/u1 underground-belt 2.5,0.5 N net=a ug=out"""), CAT)
        self.assertEqual(succ(g, "a/s0"), {("a/u0", "ug_sideload")})    # either end, never a curve
        self.assertEqual(succ(g, "a/s1"), {("a/u1", "ug_sideload")})

    def test_splitter(self):
        g = graph(L("""
            e s/in transport-belt 1.5,0.5 E net=a
            e s/sp splitter 2.5,1 E net=a
            e s/o0 transport-belt 3.5,0.5 E net=a
            e s/o1 transport-belt 3.5,1.5 E net=a
            e s/side transport-belt 2.5,2.5 N net=a"""), CAT)
        self.assertEqual(succ(g, "s/in"), {("s/sp", "belt")})
        self.assertEqual(succ(g, "s/sp"), {("s/o0", "belt"), ("s/o1", "belt")})
        self.assertEqual(succ(g, "s/side"), set())                   # a splitter takes no side-load
        self.assertEqual(g.reach({"s/in"}, "a"), {"s/in", "s/sp", "s/o0", "s/o1"})


class UndergroundTest(unittest.TestCase):
    def test_pairs_through_other_entities(self):
        g = graph(L("""
            e a/u0 underground-belt 0.5,0.5 E net=a ug=in
            e b/u0 underground-belt 2.5,0.5 S net=b ug=in
            e b/u1 underground-belt 2.5,3.5 S net=b ug=out
            e c/b0 transport-belt 3.5,0.5 N net=c
            e a/u1 underground-belt 5.5,0.5 E net=a ug=out
            e a/b0 transport-belt 6.5,0.5 E net=a"""), CAT)
        self.assertEqual(g.pairs, {"a/u0": "a/u1", "a/u1": "a/u0", "b/u0": "b/u1",
                                   "b/u1": "b/u0"})
        self.assertEqual(succ(g, "a/u0"), {("a/u1", "ug")})
        self.assertEqual(succ(g, "a/u1"), {("a/b0", "belt")})
        self.assertEqual(leaks(connect(g, CAT)), [])

    def test_max_distance_from_the_catalog(self):
        g = graph(L("""
            e y/u0 underground-belt 0.5,0.5 E net=y ug=in
            e y/u1 underground-belt 5.5,0.5 E net=y ug=out
            e n/u0 underground-belt 0.5,2.5 E net=n ug=in
            e n/u1 underground-belt 6.5,2.5 E net=n ug=out
            e f/u0 fast-underground-belt 0.5,4.5 E net=f ug=in
            e f/u1 fast-underground-belt 7.5,4.5 E net=f ug=out"""), CAT)
        self.assertEqual(g.pairs, {"y/u0": "y/u1", "y/u1": "y/u0", "f/u0": "f/u1",
                                   "f/u1": "f/u0"})                  # 5 and 7 reach; 6 does not
        self.assertEqual(g.unpaired, ["n/u0", "n/u1"])

    def test_another_tier_in_between_is_passed(self):
        g = graph(L("""
            e a/u0 underground-belt 0.5,0.5 E net=a ug=in
            e b/u0 fast-underground-belt 1.5,0.5 E net=b ug=in
            e b/u1 fast-underground-belt 3.5,0.5 E net=b ug=out
            e a/u1 underground-belt 5.5,0.5 E net=a ug=out"""), CAT)
        self.assertEqual(g.pairs, {"a/u0": "a/u1", "a/u1": "a/u0", "b/u0": "b/u1",
                                   "b/u1": "b/u0"})

    def test_the_same_tier_in_between_decides(self):
        # v4's rule: the first underground of the same name and direction decides, whatever its
        # kind. b's input stands first in a's way, so a's ends stay alone and b pairs with b.
        g = graph(L("""
            e a/u0 underground-belt 0.5,0.5 E net=a ug=in
            e b/u0 underground-belt 1.5,0.5 E net=b ug=in
            e b/u1 underground-belt 3.5,0.5 E net=b ug=out
            e a/u1 underground-belt 5.5,0.5 E net=a ug=out"""), CAT)
        self.assertEqual(g.pairs, {"b/u0": "b/u1", "b/u1": "b/u0"})
        self.assertEqual(g.unpaired, ["a/u0", "a/u1"])
        rep = connect(g, CAT)
        self.assertEqual(leaks(rep), [])
        self.assertEqual(rep.nets["a"].unpaired, ["a/u0", "a/u1"])


class InserterTest(unittest.TestCase):
    LAYOUT = """
        e a/b0 transport-belt 1.5,0.5 N net=a
        e a/b1 transport-belt 1.5,1.5 N net=a
        e c/b0 transport-belt 0.5,1.5 N net=c
        e i/f fast-inserter 2.5,0.5 W net=a
        e i/l long-handed-inserter 2.5,1.5 W net=c
        e i/o inserter 2.5,2.5 E net=o
        e o/b0 transport-belt 1.5,2.5 S net=o
        e m/m assembling-machine-1 4.5,1.5 recipe=iron-gear-wheel"""

    def test_pickup_and_drop_tiles(self):
        g = graph(L(self.LAYOUT), CAT)
        self.assertEqual(succ(g, "a/b0"), {("i/f", "pickup")})
        self.assertEqual(succ(g, "i/f"), {("m/m", "drop")})
        self.assertEqual(succ(g, "c/b0"), {("i/l", "pickup")})      # reaches over a/b1
        self.assertEqual(succ(g, "i/l"), {("m/m", "drop")})
        self.assertEqual(succ(g, "a/b1"), {("a/b0", "belt")})       # not picked by the long arm
        self.assertEqual(succ(g, "m/m"), {("i/o", "pickup")})
        self.assertEqual(succ(g, "i/o"), {("o/b0", "drop")})
        self.assertEqual(g.inserter_tiles("i/l"), ((0, 1), (4, 1)))

    def test_no_drop_on_an_underground_output(self):
        # B-120 (v4, d6018d3): an underground output's edge is not a belt surface.
        g = graph(L("""
            e c/c iron-chest 0.5,2.5
            e i/a fast-inserter 0.5,1.5 S net=a
            e a/u0 underground-belt 0.5,0.5 E net=a ug=in
            e c/d iron-chest 3.5,2.5
            e i/b fast-inserter 3.5,1.5 S net=b
            e b/u1 underground-belt 3.5,0.5 W net=b ug=out"""), CAT)
        self.assertEqual(succ(g, "i/a"), {("a/u0", "drop")})
        self.assertEqual(succ(g, "i/b"), set())

    def test_drills_drop_in_front(self):
        g = graph(L("""
            e d/m0 electric-mining-drill 1.5,1.5 S resource=iron-ore
            e d/b0 transport-belt 1.5,3.5 E net=ore
            e d/m1 burner-mining-drill 5,1 S resource=iron-ore
            e d/b1 transport-belt 5.5,2.5 W net=ore
            e d/m2 electric-mining-drill 9.5,1.5 W resource=iron-ore
            e d/f0 stone-furnace 7,1 recipe=iron-plate"""), CAT)
        self.assertEqual(succ(g, "d/m0"), {("d/b0", "mine")})
        self.assertEqual(succ(g, "d/m1"), {("d/b1", "mine")})       # the left tile, as it faces
        self.assertEqual(succ(g, "d/m2"), {("d/f0", "mine")})       # straight into a furnace


class NetTest(unittest.TestCase):
    BELT_ROUTE = """
        e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
        e r/o0 fast-inserter 1.5,3.5 N net=p
        e r/b0 transport-belt 1.5,4.5 E net=p
        e r/b1 transport-belt 2.5,4.5 E net=p
        e r/b2 transport-belt 3.5,4.5 E net=p
        e r/b3 transport-belt 4.5,4.5 E net=p
        e r/b4 transport-belt 5.5,4.5 E net=p
        e r/f0 fast-inserter 5.5,5.5 N net=p
        e m/b assembling-machine-1 5.5,7.5 recipe=transport-belt
        e r/f1 fast-inserter 9.5,4.5 W net=p
        e m/c assembling-machine-1 11.5,4.5 recipe=transport-belt"""
    NETS = {"p": ([("m/a", "iron-gear-wheel")],
                  [("m/b", "iron-gear-wheel"), ("m/c", "iron-gear-wheel")])}

    def test_direct_insertion_is_a_route(self):
        rep = connect(L("""
            e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
            e x/i0 fast-inserter 3.5,1.5 W net=g
            e m/b assembling-machine-1 5.5,1.5 recipe=transport-belt"""), CAT,
            {"g": ([("m/a", "iron-gear-wheel")], [("m/b", "iron-gear-wheel")])})
        net = rep.nets["g"]
        self.assertTrue(net.connected)
        self.assertEqual((net.pairs, net.reached, net.carriers, net.segments), (1, 1, 1, 1))
        self.assertEqual(rep.checks, [])

    def test_open_net(self):
        rep = connect(L(self.BELT_ROUTE), CAT, self.NETS)
        net = rep.nets["p"]
        self.assertFalse(net.connected)
        self.assertEqual(net.status, "open")
        self.assertEqual((net.pairs, net.reached, net.unreached), (2, 1, [("m/a", "m/c")]))
        self.assertEqual(net.segments, 2)                           # r/f1 stands alone
        self.assertEqual([str(c) for c in rep.checks],
                         ["OPEN        net p: 1 of 2 driver->consumer pairs connected; unreached "
                          "m/a -> m/c; 2 segments, 8 carriers"])

    def test_closing_the_gap_connects(self):
        gap = "".join(f"\ne r/g{j} transport-belt {6.5 + j},4.5 E net=p" for j in range(3))
        rep = connect(L(self.BELT_ROUTE.replace("\n        e r/f1", gap + "\ne r/f1")), CAT,
                      self.NETS)
        self.assertTrue(rep.nets["p"].connected)
        self.assertEqual(rep.checks, [])

    def test_unrouted_net_and_a_missing_endpoint(self):
        rep = connect(L(self.BELT_ROUTE), CAT,
                      {"p": ([("m/a", "iron-gear-wheel")], [("m/c", "iron-gear-wheel"),
                                                            ("ins/m0", "iron-gear-wheel")])})
        net = rep.nets["p"]
        self.assertEqual((net.status, net.pairs, net.reached, net.missing),
                         ("unrouted", 2, 0, ["ins/m0"]))
        self.assertEqual([str(c) for c in rep.checks],
                         ["UNROUTED    net p: 0 of 2 driver->consumer pairs connected; 2 segments, "
                          "8 carriers; not in the layout: ins/m0",
                          "LEAK        net p: r/f0 drops into m/b, which is not a consumer of p"])

    def test_an_underground_side_load_connects_and_draws_no_line(self):
        # 2.0: whether its items get through is the lane graph's to say (the routed LANE line);
        # V1 warned UG_SIDELOAD on every one
        rep = connect(L("""
            e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
            e r/o0 fast-inserter 1.5,3.5 N net=p
            e r/b0 transport-belt 1.5,4.5 E net=p
            e r/u0 underground-belt 2.5,4.5 S net=p ug=in
            e r/u1 underground-belt 2.5,7.5 S net=p ug=out
            e r/b1 transport-belt 2.5,8.5 S net=p
            e r/f0 fast-inserter 2.5,9.5 N net=p
            e m/b assembling-machine-1 2.5,11.5 recipe=transport-belt"""), CAT,
            {"p": ([("m/a", "iron-gear-wheel")], [("m/b", "iron-gear-wheel")])})
        net = rep.nets["p"]
        self.assertTrue(net.connected)
        self.assertEqual(net.ug_sideloads, [("r/b0", "r/u0")])
        self.assertEqual([str(c) for c in rep.checks], [])

    def test_endpoints_inferred_without_a_netlist(self):
        rep = connect(L(self.BELT_ROUTE), CAT)
        net = rep.nets["p"]
        self.assertEqual((net.drivers, net.consumers), (["m/a"], ["m/b", "m/c"]))
        self.assertEqual(net.status, "open")

    def test_checks_never_raise(self):
        rep = connect(L("""
            e a/b0 transport-belt 0.5,0.5 net=a
            e a/b1 transport-belt 0.5,0.5 E net=a
            e a/x nonsense-belt 1.5,0.5 E net=a
            e a/b2 transport-belt 2.5,0.5 E
            e a/i fast-inserter 3.5,0.5 NE net=a
            e a/u underground-belt 4.5,0.5 E net=a"""), CAT, {"a": ([("m/x", "coal")], [])})
        self.assertEqual(rep.nets["a"].status, "unrouted")
        problems = "\n".join(rep.graph.problems)
        self.assertIn("a/x: unknown prototype nonsense-belt", problems)
        self.assertIn("a/b1: tile 0,0 is already a/b0", problems)
        self.assertIn("a/u: an underground with no ug=in|out", problems)


class LeakTest(unittest.TestCase):
    def test_a_belt_feeds_another_nets_belt(self):
        rep = connect(L("""
            e a/b0 transport-belt 0.5,0.5 E net=a
            e b/b0 transport-belt 1.5,0.5 E net=b"""), CAT)
        self.assertEqual(leaks(rep), ["LEAK        net a: a/b0 feeds b/b0 (net b)"])

    def test_a_side_load_onto_another_nets_belt(self):
        rep = connect(L("""
            e b/b0 transport-belt 0.5,1.5 E net=b
            e b/b1 transport-belt 1.5,1.5 E net=b
            e a/s0 transport-belt 1.5,0.5 S net=a"""), CAT)
        self.assertEqual(leaks(rep), ["LEAK        net a: a/s0 side-loads onto b/b1 (net b)"])

    def test_a_side_load_onto_another_nets_underground(self):
        rep = connect(L("""
            e a/s0 transport-belt 0.5,0.5 E net=a
            e b/u0 underground-belt 1.5,0.5 S net=b ug=in"""), CAT)
        self.assertEqual([str(c) for c in rep.checks if c.code != "UNROUTED"],
                         ["LEAK        net a: a/s0 side-loads onto b/u0 (net b)"])

    def test_a_splitter_feeds_another_nets_belt(self):
        rep = connect(L("""
            e a/in transport-belt 1.5,0.5 E net=a
            e a/sp splitter 2.5,1 E net=a
            e a/o0 transport-belt 3.5,0.5 E net=a
            e b/b0 transport-belt 3.5,1.5 E net=b"""), CAT)
        self.assertEqual(leaks(rep), ["LEAK        net a: a/sp feeds b/b0 (net b)"])

    def test_an_inserter_picks_from_another_nets_belt(self):
        rep = connect(L("""
            e a/b0 transport-belt 1.5,0.5 N net=a
            e b/i0 fast-inserter 2.5,0.5 W net=b
            e m/m assembling-machine-1 4.5,1.5 recipe=iron-gear-wheel"""), CAT)
        self.assertEqual(leaks(rep), ["LEAK        net a: b/i0 (net b) picks from a/b0"])

    def test_an_inserter_feeds_a_machine_of_another_net(self):
        rep = connect(L("""
            e a/b0 transport-belt 1.5,0.5 N net=a
            e a/i0 fast-inserter 2.5,0.5 W net=a
            e m/m assembling-machine-1 4.5,1.5 recipe=iron-gear-wheel"""), CAT,
            {"a": ([], [("m/other", "iron-plate")]), "b": ([], [("m/m", "iron-plate")])})
        self.assertEqual(leaks(rep), ["LEAK        net a: a/i0 drops into m/m, which is not a "
                                      "consumer of a"])

    def test_an_underground_pairs_with_another_nets(self):
        rep = connect(L("""
            e a/u0 underground-belt 0.5,0.5 E net=a ug=in
            e b/u1 underground-belt 2.5,0.5 E net=b ug=out
            e a/u1 underground-belt 5.5,0.5 E net=a ug=out"""), CAT)
        self.assertEqual(rep.graph.pairs, {"a/u0": "b/u1", "b/u1": "a/u0"})
        self.assertEqual(leaks(rep), ["LEAK        net a: a/u0 pairs underground with b/u1 "
                                      "(net b)"])
        self.assertEqual(rep.nets["a"].unpaired, ["a/u1"])

    def test_nets_are_per_factory_on_a_surface(self):
        line = "inst x Literal at 0,0 rot 0 sig -\n" + "\n".join(
            f"e x/b{j} transport-belt {j + 0.5},0.5 E net=a" for j in range(3))
        main = fkp.loads("fkp 1 factory main\nsize 3x1\n" + line)
        boot = fkp.loads("fkp 1 factory boot\nsize 3x1\n" + line)
        surface = fkp.loads("fkp 1 surface s\nplot main at 0,0 rot 0 size 3x1\n"
                            "plot boot at 3,0 rot 0 size 3x1\n")
        rep = connect(compose.compose(surface, {"main": main, "boot": boot}, CAT), CAT)
        self.assertEqual(sorted(rep.nets), ["boot/a", "main/a"])
        self.assertEqual(leaks(rep), ["LEAK        net main/a: s:main/x/b2 feeds s:boot/x/b0 "
                                      "(net boot/a)"])


class RedgreenTest(unittest.TestCase):
    """games/spm10/redgreen.fkp: the rows' own segments, no routes between them yet."""

    @classmethod
    def setUpClass(cls):
        cls.flat = elaborate_file(os.path.join(GAME, "redgreen.fk"), CAT)
        cls.lay = fkp.load(os.path.join(GAME, "redgreen.fkp"))
        cls.rep = connect(cls.lay, CAT, endpoints(cls.flat))

    def test_every_row_segment_connects_its_attach_point_to_its_machines(self):
        g = self.rep.graph
        machines = {k for k, n in g.nodes.items() if not n.carrier}
        roles = 0
        for path, rec in self.lay.insts.items():
            frag, binding = expand.fragment_of(self.flat, path, CAT)
            for name, role in frag.roles.items():
                (ax, ay, ad), = role.attach
                x, y, _d = compose.turn(ax, ay, ad, rec.rot, frag.size)
                at = g.at[(int(x + rec.x), int(y + rec.y))]
                self.assertEqual(g.nodes[at].net, binding[name], (path, name))
                reached = g.reach({at}, binding[name], forward=role.side == "in")
                self.assertEqual(reached & machines, {f"{path}/{m}" for m in role.machines},
                                 (path, name))
                roles += 1
        self.assertEqual((len(self.lay.insts), roles), (14, 31))

    def test_every_net_between_rows_is_unrouted(self):
        self.assertEqual(len(self.rep.nets), 12)
        self.assertEqual({n: r.status for n, r in self.rep.nets.items()},
                         {n: "unrouted" for n in self.flat.nets})
        self.assertEqual(leaks(self.rep), [])
        self.assertEqual(self.rep.graph.problems, [])
        # (segments, carriers, driver->consumer pairs): one segment per row role on the net
        segs = {n: (r.segments, r.carriers, r.pairs) for n, r in self.rep.nets.items()}
        self.assertEqual(segs, {
            "iron_ore": (2, 62, 160), "copper_ore": (2, 23, 24), "iron_fuel": (2, 50, 32),
            "copper_fuel": (2, 20, 6), "iron": (5, 76, 112), "copper": (3, 54, 54),
            "gear": (4, 37, 21), "cable": (2, 23, 8), "circ": (2, 11, 2), "belt": (2, 28, 6),
            "ins_": (2, 27, 6), "packs": (3, 84, 110)})
        self.assertEqual([r.missing for r in self.rep.nets.values()], [[]] * 12)
        self.assertEqual(self.rep.summary(), "12 nets: 0 connected, 0 open, 12 unrouted; 0 LEAK; "
                         "566 entities, 617 edges, 0 underground pairs")

    def test_the_same_on_a_surface(self):
        surface = fkp.loads("fkp 1 surface nauvis\nplot redgreen at 100,50 rot 1 size 43x46\n")
        s = compose.compose(surface, {"redgreen": self.lay}, CAT)
        rep = connect(s, CAT, endpoints(self.flat, surface="nauvis", factory="redgreen"))
        self.assertEqual({n: r.status for n, r in rep.nets.items()},
                         {f"redgreen/{n}": "unrouted" for n in self.flat.nets})
        self.assertEqual(leaks(rep), [])
        self.assertEqual({n[len("redgreen/"):]: (r.segments, r.carriers, r.pairs)
                          for n, r in rep.nets.items()},
                         {n: (r.segments, r.carriers, r.pairs) for n, r in self.rep.nets.items()})


class SinkTest(unittest.TestCase):
    """2.0.12: each maker's product reaches a sink (the solo run's Mall4 went out with its
    products belt unrouted, 2026-10-23 23:23), and a net nothing uses is UNUSED, not UNROUTED (the
    build script stops on UNROUTED by default now)."""

    MAKERS = """
        e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel
        e x/i0 fast-inserter 3.5,1.5 W net=g
        e m/k wooden-chest 4.5,1.5
        e m/z assembling-machine-1 1.5,8.5 recipe=iron-gear-wheel"""
    NETS = {"g": ([("m/a", "iron-gear-wheel"), ("m/z", "iron-gear-wheel")],
                  [("m/k", "iron-gear-wheel")])}

    def test_a_maker_cut_off_from_its_sink(self):
        from fkcore.connect import cut_off
        rep = connect(L(self.MAKERS), CAT, self.NETS)
        self.assertEqual(rep.nets["g"].status, "open")
        self.assertEqual(cut_off(rep, {"m/a", "m/z"}), [("m/z", "g", 1)])
        self.assertEqual(cut_off(rep, {"m/a"}), [])          # only the makers asked about

    def test_the_report_line_and_no_sink(self):
        from types import SimpleNamespace
        from fkcore import flow
        from fkcore.elaborate import Machine

        def machine(key, proto, makes, source=False):
            return Machine(key, key.split("/")[0], "Asm", proto, None, {}, makes, None, False,
                           None, source, 1.0)
        flat = SimpleNamespace(machines={
            "m/a": machine("m/a", "assembling-machine-1", {"iron-gear-wheel": 1}),
            "m/z": machine("m/z", "assembling-machine-1", {"iron-gear-wheel": 1}),
            "m/k": machine("m/k", "wooden-chest", {})})
        ctx = SimpleNamespace(cat=CAT)
        lines, checks = flow._sinks(ctx, "mall", flat, connect(L(self.MAKERS), CAT, self.NETS))
        self.assertEqual(lines, ["  sinks     1 of 2 makers on a net reach a sink with what they "
                                 "make; none reached: m/z (net g)"])
        self.assertEqual([str(c) for c in checks],
                         ["NO_SINK     mall m/z: what it makes reaches none of the 1 consumer of "
                          "net g: it has nowhere to go"])
        # a net none of whose pairs connect: its UNROUTED line says it, the report line too
        lines, checks = flow._sinks(ctx, "mall", flat, connect(L(self.MAKERS.replace(
            "e x/i0 fast-inserter 3.5,1.5 W net=g", "")), CAT, self.NETS))
        self.assertIn("0 of 2 makers on a net reach a sink", lines[0])
        self.assertEqual(checks, [])

    def test_a_net_nothing_uses_is_unused(self):
        rep = connect(L("e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel"), CAT,
                      {"coalin": ([], [])})
        self.assertEqual([str(c) for c in rep.checks],
                         ["UNUSED      net coalin: no driver->consumer pair to connect (0 drivers, "
                          "0 consumers); 0 segments, 0 carriers"])
        rep = connect(L("e m/a assembling-machine-1 1.5,1.5 recipe=iron-gear-wheel"), CAT,
                      {"g": ([("m/a", "iron-gear-wheel")], [])})
        self.assertEqual([c.code for c in rep.checks], ["UNROUTED"])     # it makes, nothing takes


if __name__ == "__main__":
    unittest.main()
