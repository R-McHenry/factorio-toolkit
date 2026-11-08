"""Belt tiers per connector (fkcore.tiers, CORE-V2.md "Tier per connector", Rory): minimize,
maximize and only yellow, with budgets, from the flow solver's required flows."""
import unittest
from dataclasses import replace

from fkcore import connect, expand, fkp, lanes, lang, route, routed, tiers
from fkcore import throughput as tp
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
ORE = "iron-ore"


def L(rows):
    return fkp.loads("fkp 1 factory t\n" + "\n".join(rows))


def miner_line(red=()):
    """Rory's case: 18 drills (0.5 ore/s each) above an east belt, then 29 furnaces below it fed
    by fast inserters; 9 ore/s made, all on the belt's left lane. -> (layout, lane graph, supply,
    demand)."""
    rows, supply, demand = [], {}, {}
    for k in range(18):
        rows.append(f"e d/m{k} electric-mining-drill {3 * k + 1.5},1.5 S")
        supply[(f"d/m{k}", "")] = {ORE: 0.5}
    for k in range(29):
        x = 54 + 2 * k
        rows += [f"e f/i{k} fast-inserter {x}.5,4.5 N net=ore", f"e f/m{k} stone-furnace {x + 1},6"]
        demand[(f"f/m{k}", "")] = {ORE: 0.3125}
    for x in range(112):
        name = "fast-transport-belt" if x in red else "transport-belt"
        rows.append(f"e a/b{x} {name} {x}.5,3.5 E net=ore")
    lay = L(rows)
    return lay, lanes.build(lay, CAT), supply, demand


def red_tiles(chosen):
    return sorted(int(k[3:]) for k, t in chosen.items() if t == 1 and k.startswith("a/b"))


def line(rows, supply, demand):
    """rows -> (layout, lane graph, required flows); ore fed onto and drained from the left lane
    of the given belts."""
    lay = L(rows)
    lg = lanes.build(lay, CAT)
    req = tp.solve(lg, supply={(k, "L"): {ORE: v} for k, v in supply.items()},
                   demand={(k, "L"): {ORE: float("inf")} for k in demand}).required
    return lay, lg, req


def renamed(lay, chosen):
    """The layout's entities with the chosen tiers."""
    out = []
    for k, e in lay.entities.items():
        if k in chosen:
            e = replace(e, name=tiers.FAMILY[tiers.tier_of(e.name)[0]][chosen[k]])
        out.append(e)
    return out


def delivered(red):
    lay, lg, supply, demand = miner_line(red)
    r = tp.solve(lg, supply=supply, demand=demand)
    return sum(r.delivered.get(v, {}).get(ORE, 0.0) for v in demand)


class MinerLineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lay, cls.lg, supply, demand = miner_line()
        cls.req = tp.solve(cls.lg, supply=supply, demand=demand).required

    def choose(self, mode="minimize", allow=tiers.TIERS, budgets=None):
        return tiers.choose(self.lg, self.req, CAT, self.lay.entities, mode, allow, budgets)

    def test_minimize_puts_red_in_the_middle(self):
        chosen, notes = self.choose()
        self.assertEqual(red_tiles(chosen), list(range(46, 63)))       # 17: tiles 46 to 62
        self.assertEqual(notes, [])
        self.assertAlmostEqual(delivered(red_tiles(chosen)), 9.0, places=6)
        self.assertAlmostEqual(delivered(()), 7.5, places=6)

    def test_a_budget_that_covers_the_stretch(self):
        chosen, notes = self.choose(budgets={"red": 17})
        self.assertEqual(red_tiles(chosen), list(range(46, 63)))
        self.assertEqual(notes, [])

    def test_a_short_budget_keeps_the_peak(self):
        chosen, notes = self.choose(budgets={"red": 10})
        red = red_tiles(chosen)
        self.assertEqual(len(red), 10)
        self.assertEqual(red, list(range(red[0], red[0] + 10)))     # one stretch, around the peak
        self.assertTrue(red[0] <= 52 <= red[-1])                       # the last drill's tile
        self.assertIn("the red budget (10) takes 10 of the 17 entities that want red", notes[0])
        self.assertGreater(delivered(red), 7.5 + 0.1)
        self.assertAlmostEqual(delivered(list(range(5)) + list(range(107, 112))), 7.5, places=6)

    def test_maximize_and_only_yellow(self):
        chosen, _notes = self.choose("maximize", allow=("yellow", "red"))
        carrying = [x for x in range(112) if sum(self.req.get((f"a/b{x}", "L"), {}).values()) > 0]
        self.assertEqual(red_tiles(chosen), carrying)
        chosen, _notes = self.choose("yellow")
        self.assertEqual(red_tiles(chosen), [])

    def test_maximize_all_takes_the_belts_that_carry_nothing_on_paper(self):
        # 2.1.31: a lab's fed ports and Literal belts have no rate on paper, so plain maximize
        # left the whole PU bay yellow; --all (every=True) takes the top tier everywhere
        chosen, _notes = tiers.choose(self.lg, self.req, CAT, self.lay.entities, "maximize",
                                      ("yellow", "red"), every=True)
        self.assertEqual(red_tiles(chosen), list(range(112)))

    def test_more_than_the_fastest_allowed(self):
        chosen, notes = self.choose(allow=("yellow",))
        self.assertEqual(red_tiles(chosen), [])
        self.assertIn("17 entities need more than yellow carries (up to 9.00/s a lane)", notes[0])


class UndergroundPairTest(unittest.TestCase):
    def test_a_tunnel_changes_tier_as_one(self):
        # 10/s on one lane through a tunnel under a wall of chests: both ends go red together
        rows = ["e a/b0 transport-belt 0.5,0.5 E net=a", "e a/u0 underground-belt 1.5,0.5 E net=a ug=in",
                "e a/u1 underground-belt 4.5,0.5 E net=a ug=out", "e a/b1 transport-belt 5.5,0.5 E net=a"]
        rows += [f"e w/c{k} wooden-chest {x}.5,0.5" for k, x in enumerate((2, 3))]
        lay = L(rows)
        lg = lanes.build(lay, CAT)
        req = tp.solve(lg, supply={("a/b0", "L"): {ORE: 10}},
                       demand={("a/b1", "L"): {ORE: float("inf")}}).required
        chosen, _notes = tiers.choose(lg, req, CAT, lay.entities)
        self.assertEqual({k: t for k, t in chosen.items()}, {"a/b0": 1, "a/u0": 1, "a/u1": 1,
                                                            "a/b1": 1})
        for budget in (1, 2, 3):                                        # a pair counts as two
            chosen, _notes = tiers.choose(lg, req, CAT, lay.entities, budgets={"red": budget})
            self.assertEqual(chosen["a/u0"], chosen["a/u1"])
            self.assertLessEqual(sum(chosen.values()), budget)
        chosen, _notes = tiers.choose(lg, req, CAT, lay.entities, budgets={"red": 4})
        self.assertEqual(sum(chosen.values()), 4)


class NoDowngradeTest(unittest.TestCase):
    """minimize and maximize never take a tier away unless asked (downgrade=True)."""

    def setUp(self):
        rows = [f"e a/b{x} fast-transport-belt {x}.5,0.5 E net=a" for x in range(4)]
        self.lay, self.lg, self.req = line(rows, {"a/b0": 2}, ["a/b3"])

    def choose(self, **kw):
        return tiers.choose(self.lg, self.req, CAT, self.lay.entities, **kw)

    def test_red_that_yellow_would_carry_stays_red(self):
        chosen, notes = self.choose()
        self.assertEqual(set(chosen.values()), {1})
        self.assertEqual(notes, [])
        chosen, _notes = self.choose(mode="maximize", allow=("yellow",))
        self.assertEqual(set(chosen.values()), {1})
        chosen, _notes = self.choose(downgrade=True)
        self.assertEqual(set(chosen.values()), {0})
        chosen, _notes = self.choose(mode="yellow")                 # asked for: always yellow
        self.assertEqual(set(chosen.values()), {0})

    def test_a_budget_never_takes_what_is_there(self):
        chosen, notes = self.choose(budgets={"red": 2})
        self.assertEqual(set(chosen.values()), {1})
        self.assertEqual(notes, ["4 entities already red keep it: the red budget (2) is over by 2"])


class TunnelReachTest(unittest.TestCase):
    def test_a_red_tunnel_longer_than_yellow_reaches(self):
        # red ends 6 apart (yellow reaches 5), 1/s: the belts go yellow, the pair stays red
        rows = ["e a/b0 fast-transport-belt 0.5,0.5 E net=a",
                "e a/u0 fast-underground-belt 1.5,0.5 E net=a ug=in",
                "e a/u1 fast-underground-belt 7.5,0.5 E net=a ug=out",
                "e a/b1 fast-transport-belt 8.5,0.5 E net=a"]
        lay, lg, req = line(rows, {"a/b0": 1}, ["a/b1"])
        self.assertEqual(lg.graph.pairs["a/u0"], "a/u1")
        for mode in ("minimize", "yellow"):
            chosen, notes = tiers.choose(lg, req, CAT, lay.entities, mode, downgrade=True)
            self.assertEqual(chosen, {"a/b0": 0, "a/u0": 1, "a/u1": 1, "a/b1": 0})
            self.assertIn("1 underground pair at the slowest tier that reaches its tunnel: "
                          "a/u0 (6 tiles, red)", notes)


class PairingTest(unittest.TestCase):
    """On one row: yellow pair A (1 -> 4) with red pair B (3 -> 7) interleaved, legal since
    different names pass under each other. A carries 10/s and wants red; red A's entrance would
    meet B's red entrance first and lose its exit to it, so A goes back to yellow."""

    def setUp(self):
        rows = ["e a/b0 transport-belt 0.5,0.5 E net=a",
                "e a/u0 underground-belt 1.5,0.5 E net=a ug=in",
                "e b/b0 fast-transport-belt 2.5,0.5 E net=b",
                "e b/u0 fast-underground-belt 3.5,0.5 E net=b ug=in",
                "e a/u1 underground-belt 4.5,0.5 E net=a ug=out",
                "e a/b1 transport-belt 5.5,0.5 E net=a",
                "e b/u1 fast-underground-belt 7.5,0.5 E net=b ug=out",
                "e b/b1 fast-transport-belt 8.5,0.5 E net=b"]
        self.lay, self.lg, self.req = line(rows, {"a/b0": 10, "b/b0": 1}, ["a/b1", "b/b1"])
        self.pairs = connect.graph(self.lay, CAT).pairs
        self.assertEqual((self.pairs["a/u0"], self.pairs["b/u0"]), ("a/u1", "b/u1"))

    def test_a_change_that_steals_a_partner_is_reverted(self):
        chosen, notes = tiers.choose(self.lg, self.req, CAT, self.lay.entities)
        self.assertEqual((chosen["a/b0"], chosen["a/b1"]), (1, 1))     # the belts still go red
        self.assertEqual({k: chosen[k] for k in ("a/u0", "a/u1", "b/u0", "b/u1")},
                         {"a/u0": 0, "a/u1": 0, "b/u0": 1, "b/u1": 1})
        self.assertIn("reverted 1 underground pair whose pairing a tier change would alter: "
                      "a/u0, a/u1", notes)
        self.assertEqual(connect.graph(renamed(self.lay, chosen), CAT).pairs, self.pairs)

    def test_a_swap_that_keeps_the_pairing_stands(self):
        # with downgrade B goes yellow too: red A and yellow B pair as before, nothing reverted
        chosen, notes = tiers.choose(self.lg, self.req, CAT, self.lay.entities, downgrade=True)
        self.assertEqual({k: chosen[k] for k in ("a/u0", "a/u1", "b/u0", "b/u1")},
                         {"a/u0": 1, "a/u1": 1, "b/u0": 0, "b/u1": 0})
        self.assertFalse(any("reverted" in n for n in notes))
        self.assertEqual(connect.graph(renamed(self.lay, chosen), CAT).pairs, self.pairs)


class PinnedTest(unittest.TestCase):
    def test_pinned_entities_keep_their_tier(self):
        # assign pins a Literal's entities: fixed = the keys whose owner is a Literal instance.
        # A pinned underground end pins its partner.
        rows = ["e a/b0 fast-transport-belt 0.5,0.5 E net=a",
                "e a/u0 fast-underground-belt 1.5,0.5 E net=a ug=in",
                "e a/u1 fast-underground-belt 4.5,0.5 E net=a ug=out",
                "e a/b1 fast-transport-belt 5.5,0.5 E net=a",
                "e a/b2 fast-transport-belt 6.5,0.5 E net=a"]
        lay, lg, req = line(rows, {"a/b0": 1}, ["a/b2"])
        chosen, _notes = tiers.choose(lg, req, CAT, lay.entities, downgrade=True,
                                      fixed={"a/b0", "a/u0"})
        self.assertEqual(chosen, {"a/b1": 0, "a/b2": 0})
        chosen, _notes = tiers.choose(lg, req, CAT, lay.entities, mode="yellow",
                                      fixed={"a/b0", "a/u0"})
        self.assertEqual(chosen, {"a/b1": 0, "a/b2": 0})


SMELTER = """
ore   = MinerRow<n=18, resource=iron-ore> @(31, 7, rot 2)
coal  = MinerRow<n=2, resource=coal>      @(37, 7, rot 2)
smelt = SmelterRow<n=26, recipe=iron-plate> @(4, 11)
c1 = Chest<provider> @(1, 24)
c2 = Chest<provider> @(1, 26)
c3 = Chest<provider> @(1, 28)
c4 = Chest<provider> @(1, 30)
net ore_: ore -> smelt
net fuel: coal -> smelt
net plates: smelt -> c1, c2, c3, c4
"""


class SmelterRowTest(unittest.TestCase):
    """26 furnaces drop their plates on the far lane of their row's belt: 8.1/s where a yellow lane
    carries 7.5. minimize turns red just the belts that carry more than that."""

    @classmethod
    def setUpClass(cls):
        f = lang.parse(SMELTER, "t.fk")
        cls.flat = elaborate(f, dict(f.modules), CAT, "t")
        lay, _notes = expand.expand_factory(cls.flat, CAT)
        cls.lay = route.route_layout(cls.flat, lay, CAT).layout

    def plates(self, lay):
        r = routed.solve(self.flat, lay, CAT)
        return sum(r.res.delivered.get((f"c{k}/c0", ""), {}).get("iron-plate", 0.0)
                   for k in range(1, 5)), r

    def test_yellow_binds(self):
        got, r = self.plates(self.lay)
        self.assertAlmostEqual(got, 7.5, places=3)
        _lines, checks = routed.report(r, "t")
        self.assertEqual([c.where for c in checks], ["t net plates"])
        self.assertIn("8.12/s required where its yellow lanes carry 7.50/s (ratio 1.08)",
                      str(checks[0]))

    def test_minimize(self):
        new, lines, changed = tiers.assign(self.flat, self.lay, CAT, "minimize")
        self.assertEqual(len(changed), 11)
        self.assertTrue(all(n == "fast-transport-belt" for _o, n in changed.values()))
        self.assertEqual({self.lay.entities[k].attrs["net"] for k in changed}, {"plates"})
        self.assertIn("11 changed", lines[0])
        got, r = self.plates(new)
        self.assertAlmostEqual(got, 26 * 0.3125, places=3)
        self.assertEqual(routed.report(r, "t")[1], [])
        self.assertEqual(fkp.invariants(new, CAT, nets=self.flat.nets), [])

    def test_a_short_red_budget(self):
        new, lines, changed = tiers.assign(self.flat, self.lay, CAT, "minimize",
                                           budgets={"red": 5})
        self.assertEqual(len(changed), 5)
        self.assertIn("the red budget (5) takes 5 of the 11 entities that want red", lines[1])

    def test_a_rebuild_keeps_red(self):
        red, _lines, _changed = tiers.assign(self.flat, self.lay, CAT, "minimize")
        _new, lines, changed = tiers.assign(self.flat, red, CAT, "minimize", allow=("yellow",))
        self.assertEqual(changed, {})
        self.assertIn("11 red", lines[0])
        _new, lines, changed = tiers.assign(self.flat, red, CAT, "minimize", allow=("yellow",),
                                            downgrade=True)
        self.assertEqual(len(changed), 11)
        self.assertIn("; downgrade)", lines[0])


if __name__ == "__main__":
    unittest.main()
