"""2.1, fluid ports' data fix: recipe products' probabilities, read from the game
(``tools/read_facts.py --products``) into catalog.json. Before it the catalog had none, and
``fk rates`` gave ``uranium-processing`` a whole U-235 a craft: about 140 times too much."""
import unittest

from fkcore import cost
from fkcore.catalog import Catalog, expected
from tools import read_facts

CAT = Catalog.load()


class ProbabilityTest(unittest.TestCase):
    def test_uranium_processing_makes_the_expected_amounts(self):
        needs, makes = CAT.recipe_rates("uranium-processing", 1)       # a centrifuge is speed 1
        crafts = 1 / 12
        self.assertAlmostEqual(needs["uranium-ore"], 10 * crafts)
        self.assertAlmostEqual(makes["uranium-235"], 0.007 * crafts)
        self.assertAlmostEqual(makes["uranium-238"], 0.993 * crafts)
        self.assertAlmostEqual(CAT.craft_rate("uranium-processing", "centrifuge")["uranium-235"],
                               0.007 / 12)

    def test_every_probability_is_the_games(self):
        probs = {(r["name"], p["name"]): p["probability"]
                 for r in CAT.recipes() for p in r.get("products", ()) if "probability" in p}
        self.assertEqual(probs[("uranium-processing", "uranium-235")], 0.007)
        self.assertEqual(probs[("yumako-processing", "yumako-seed")], 0.02)
        self.assertEqual(probs[("metallic-asteroid-crushing", "metallic-asteroid-chunk")], 0.2)
        self.assertTrue(all(0 < p < 1 for p in probs.values()))
        # kovarex is certain: 41 U-235 back for 40
        self.assertAlmostEqual(CAT.recipe_rates("kovarex-enrichment-process", 1)[1]["uranium-235"],
                               41 / 60)

    def test_expected(self):
        self.assertEqual(expected({"amount": 2}), 2.0)
        self.assertAlmostEqual(expected({"amount": 1, "probability": 0.007}), 0.007)
        self.assertEqual(expected({"amount_min": 1, "amount_max": 3, "probability": 0.5}), 1.0)
        self.assertEqual(expected({"amount": 0, "extra_count_fraction": 0.25}), 0.25)

    def test_cost_counts_the_expected_amount(self):
        r = {"name": "x", "energy": 1, "ingredients": [{"name": "iron-plate", "amount": 1}],
             "products": [{"name": "x", "amount": 1, "probability": 0.5}]}

        class Fake:
            def is_fluid(self, _n):
                return False

            def has_recipe(self, n):
                return n == "x"

            def recipe(self, _n):
                return r

            def recipes(self):
                return [r]
        self.assertEqual(cost.item_cost(Fake(), "x"), 2.0)       # two crafts for one x

    def test_apply_probabilities(self):
        cat = {"recipes": [
            {"name": "uranium-processing", "products": [
                {"name": "uranium-235", "amount": 1, "type": "item"},
                {"name": "uranium-238", "amount": 1, "type": "item"}]},
            {"name": "iron-gear-wheel", "products": [{"name": "iron-gear-wheel", "amount": 1}]},
            {"name": "old", "products": [{"name": "y", "amount": 1, "probability": 0.5}]}]}
        game = {"uranium-processing": [
            {"name": "uranium-235", "type": "item", "amount": 1, "probability": 0.007000000000000001},
            {"name": "uranium-238", "type": "item", "amount": 1, "probability": 0.993}],
            "iron-gear-wheel": [{"name": "iron-gear-wheel", "type": "item", "amount": 1,
                                 "probability": 1}],
            "old": [{"name": "y", "type": "item", "amount": 1, "probability": 1}]}
        new, changes = read_facts.apply_probabilities(cat, game)
        u = new["recipes"][0]["products"]
        self.assertEqual([p.get("probability") for p in u], [0.007, 0.993])
        self.assertNotIn("probability", new["recipes"][1]["products"][0])
        self.assertNotIn("probability", new["recipes"][2]["products"][0])
        self.assertEqual(len(changes), 3)
        self.assertNotIn("probability", cat["recipes"][0]["products"][0])     # not changed in place


if __name__ == "__main__":
    unittest.main()
