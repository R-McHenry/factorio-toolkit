"""fkcore.supply and the grouped alerts, on fixture reads shaped like the first V1 run's (2026-10-20):
ghosts the network holds nothing for, recipes nobody researched, nothing researching."""
import unittest

from fkcore import alerts, link, supply
from fkcore.sense import Verdict

RED = [{"name": "automation-science-pack", "amount": 1}]


def tech(name, count, ingredients=None, trigger=None, researched=False, pre=()):
    t = {"name": name, "researched": researched, "enabled": True, "count": count,
         "ingredients": ingredients if ingredients is not None else RED,
         "prerequisites": [{"name": p, "researched": done} for p, done in pre], "unlocks": []}
    if trigger:
        t["trigger"] = trigger
    return t


RAW = {
    "tick": 124301, "force": "player", "surface": "nauvis", "networks": 1,
    "entities": [
        {"entity": "transport-belt", "item": "transport-belt", "stock": 0, "known": True,
         "enabled": True},
        {"entity": "electric-mining-drill", "item": "electric-mining-drill", "stock": 0,
         "known": True, "enabled": False,
         "tech": tech("electric-mining-drill", 25, pre=[("automation-science-pack", False)])},
        {"entity": "medium-electric-pole", "item": "medium-electric-pole", "stock": 93,
         "known": True, "enabled": False, "tech": tech("electric-energy-distribution-1", 120)},
        {"entity": "iron-chest", "item": "iron-chest", "stock": 4, "known": True, "enabled": True},
    ],
    "recipes": [{"recipe": "automation-science-pack", "known": True, "enabled": False,
                 "tech": tech("automation-science-pack", 0, [],
                              {"type": "craft-item", "item": "lab", "count": 1})}],
    "research": {"current": None, "queue": {}, "labs": 0, "researched": 4},
}


class SupplyTest(unittest.TestCase):
    def setUp(self):
        self.sup = supply.from_raw(RAW)

    def test_ghost_states(self):
        self.assertEqual(supply.ghost_state(self.sup, "transport-belt", 204)[0], "SHORT")
        state, why = supply.ghost_state(self.sup, "electric-mining-drill", 18)
        self.assertEqual(state, "LOCKED")
        self.assertIn("research electric-mining-drill (25 automation-science-pack; first: "
                      "automation-science-pack)", why)
        # in the network: robots can build it, locked recipe or not
        self.assertEqual(supply.ghost_state(self.sup, "medium-electric-pole", 10)[0], None)
        state, why = supply.ghost_state(self.sup, "iron-chest", 6)
        self.assertEqual(state, "SHORT")
        self.assertIn("the network holds 4 of 6 iron-chest", why)

    def test_mark_ghosts(self):
        vs = [Verdict("GHOST", "transport-belt", 1.5, 1.5), Verdict("GHOST", "iron-chest", 3.5, 1.5),
              Verdict("GHOST", "medium-electric-pole", 5.5, 1.5), Verdict("OK", "transport-belt", 0.5, 0.5)]
        supply.mark_ghosts(vs, self.sup)
        self.assertEqual([v.verdict for v in vs], ["GHOST SHORT", "GHOST", "GHOST", "OK"])

    def test_bom_lines_and_checks(self):
        need = {"transport-belt": 204, "electric-mining-drill": 18, "medium-electric-pole": 12}
        lines, checks = supply.bom(need, self.sup, ["automation-science-pack"])
        self.assertTrue(lines[0].startswith("STOCK: robots can build 1 of 3 kinds now; SHORT 204 "
                                            "transport-belt, 18 electric-mining-drill; LOCKED "
                                            "electric-mining-drill, recipe automation-science-pack"),
                        lines[0])
        codes = sorted((c.code, c.where) for c in checks)
        self.assertEqual(codes, [("LOCKED", "electric-mining-drill"),
                                 ("LOCKED", "recipe automation-science-pack"),
                                 ("LOW_STOCK", "electric-mining-drill"),
                                 ("LOW_STOCK", "transport-belt")])
        lock = next(c for c in checks if c.where == "recipe automation-science-pack")
        self.assertIn("craft lab x1", lock.msg)

    def test_research_line(self):
        loud = supply.research_line(self.sup.research)
        self.assertTrue(loud.startswith("RESEARCH: NONE"), loud)
        self.assertIn("0 labs", loud)
        busy = supply.research_line({"current": "automation", "progress": 0.45,
                                     "queue": ["automation", "logistics"], "labs": 2})
        self.assertEqual(busy, "research: automation 45%; queue: logistics; 2 labs")
        self.assertIn("0 labs: it will not move",
                      supply.research_line({"current": "automation", "labs": 0}))

    def test_cost_text(self):
        self.assertEqual(supply.cost_text(tech("automation-2", 40, RED + [
            {"name": "logistic-science-pack", "amount": 1}])),
            "40 automation-science-pack + 40 logistic-science-pack")
        self.assertEqual(supply.cost_text(tech("x", 0, [], {"type": "craft-item", "item": "lab",
                                                            "count": 1})), "craft lab x1")

    def test_tech_lines(self):
        data = {"asks": [{"asked": "electric-mining-drill", "kind": "recipe",
                          "recipe": "electric-mining-drill", "enabled": False,
                          "techs": [tech("electric-mining-drill", 25,
                                         pre=[("automation-science-pack", False)])]},
                         {"asked": "nope", "kind": "unknown"}]}
        out = supply.tech_lines(data)
        self.assertEqual(out[0], "electric-mining-drill: recipe LOCKED: research it first")
        self.assertIn("tech electric-mining-drill: NOT researched; cost 25 automation-science-pack; "
                      "research first: automation-science-pack", out[1])
        self.assertIn("nope: no technology, recipe or item of that name", out)

    def test_recipe_and_available_lines(self):
        rec = supply.recipe_lines({"rows": [
            {"name": "lab", "enabled": True, "by": None},
            {"name": "assembling-machine-1", "enabled": False, "by": "automation",
             "by_researched": False}]})
        self.assertEqual(rec[0], "recipes: 2 read, 1 enabled, 1 locked")
        self.assertIn("assembling-machine-1", rec[1])
        self.assertIn("by automation (not researched)", rec[1])
        av = supply.available_lines({"techs": [tech("automation", 10), tech("automation-science-pack",
                                                                           0, [], {"type": "craft-item",
                                                                                   "item": "lab"})],
                                     "research": RAW["research"]})
        self.assertTrue(av[0].startswith("RESEARCH: NONE"))
        self.assertIn("automation-science-pack", av[2])     # a trigger first: nothing to wait for

    def test_the_lua_is_safe(self):
        for lua in (supply.lua_read("player", "nauvis", ["transport-belt"], ["lab"], "t"),
                    supply.lua_tech("player", ["automation"], "t"),
                    supply.lua_recipes("player", [], "t"),
                    supply.lua_available("player", "nauvis", "t"),
                    supply.lua_add_research("player", "nauvis", ["automation"])):
            link.assert_safe(lua)
            for line in lua.splitlines():
                self.assertFalse("--" in line and not line.strip().startswith("--"), line)


class GroupedAlertsTest(unittest.TestCase):
    def test_a_ghost_flood_is_one_line_with_stock(self):
        sup = supply.from_raw(RAW)
        def entry(i, target):
            return {"alert": {"type": "no_material_for_construction", "surface": "nauvis", "x": i,
                              "y": 0, "target": target, "ghost": True, "tick": 100}, "first": 100,
                    "pushed": 100}
        new = [entry(i, "transport-belt") for i in range(204)]
        new += [entry(300 + i, "electric-mining-drill") for i in range(18)]
        out = alerts.lines(new, [], [], 200, sup)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("ALERT no_material_for_construction x222: 204 "
                                          "transport-belt (the network holds 0), 18 "
                                          "electric-mining-drill (LOCKED:"), out[0])

    def test_a_few_alerts_stay_one_line_each(self):
        e = {"alert": {"type": "entity_destroyed", "surface": "nauvis", "x": 1, "y": 2,
                       "target": "wooden-chest", "tick": 5}, "first": 5, "pushed": 5}
        self.assertEqual(alerts.lines([e], [], [], 10),
                         ["ALERT entity_destroyed: wooden-chest at nauvis 1,2 (raised at tick 5)"])


if __name__ == "__main__":
    unittest.main()
