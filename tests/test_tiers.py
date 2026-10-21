"""Belt tiers per connector (fkcore.tiers, CORE-V2.md "Tier per connector", Rory): minimize,
maximize and only yellow, with budgets, from the flow solver's required flows."""
import unittest

from fkcore import expand, fkp, lanes, lang, route, routed, tiers
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


SMELTER = """
ore   = MinerRow<n=18, resource=iron-ore> @(4, 0, rot 2)
coal  = MinerRow<n=2, resource=coal>      @(34, 0, rot 2)
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


if __name__ == "__main__":
    unittest.main()
