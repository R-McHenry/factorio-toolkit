"""The game's facts as data (2.1.1): fkcore/data/facts.json (fkcore.facts) and the widened
catalog.json, both read from the game by tools/read_facts.py.

The dicts that were Python before 2.1.1 are reads of the file now, with the game's answers.
"""
import json
import unittest

from fkcore import catalog, codec, elaborate, facts, templates
from fkcore.catalog import Catalog

CAT = Catalog.load()


class FileTest(unittest.TestCase):
    def test_the_file_loads(self):
        f = facts.load()
        self.assertEqual(f["version"], "2.0.77")
        self.assertEqual(set(f["mods"]), {"base", "elevated-rails", "quality", "space-age"})
        for key in ("entities", "resources", "fuels", "modules", "fluids", "recipes",
                    "steam_per_s", "heat_w", "circuit", "signals", "never_transmit"):
            self.assertIn(key, f)
        self.assertIs(facts.load(), f)                       # read once
        with open(facts.PATH, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), f)

    def test_every_catalog_entity_has_facts(self):
        names = {r["name"] for r in CAT._entities.values()}
        self.assertEqual(names, set(facts.load()["entities"]))
        self.assertEqual(len(names), 145)

    def test_an_unknown_name(self):
        self.assertEqual(facts.entity("no-such-thing"), {})
        self.assertIsNone(facts.energy_w("no-such-thing"))
        self.assertIsNone(facts.mining_time("no-such-ore"))
        self.assertIsNone(facts.fuel_value("no-such-fuel"))


class GameFactsTest(unittest.TestCase):
    def test_energy_and_burners(self):
        self.assertEqual(facts.energy_w("stone-furnace"), 90000)
        self.assertEqual(facts.energy_w("boiler"), 1800000)
        self.assertEqual(facts.energy_w("assembling-machine-2"), 150000)
        self.assertTrue(facts.is_burner("burner-mining-drill"))
        self.assertFalse(facts.is_burner("electric-mining-drill"))
        self.assertNotIn("biochamber", facts.burns("chemical"))     # it burns nutrients
        self.assertIn("biochamber", facts.burns("nutrients"))

    def test_steam_and_heat(self):
        steam = facts.steam_per_s()
        self.assertEqual(steam["boiler"], 60.0)
        self.assertEqual(steam["steam-engine"], 30.0)
        self.assertEqual(steam["steam-turbine"], 60.0)
        self.assertEqual(steam["heat-exchanger"], 10e6 / (485 * 200.0))
        self.assertEqual(facts.heat_w()["nuclear-reactor"], 40e6)

    def test_mining(self):
        self.assertEqual(facts.mining_radius("electric-mining-drill"), 2.49)
        self.assertEqual(facts.mining_time("uranium-ore"), 2.0)
        self.assertNotIn("crude-oil", facts.solid_resources())
        self.assertEqual(facts.load()["resources"]["uranium-ore"]["required_fluid"], "sulfuric-acid")

    def test_modules_and_productivity(self):
        self.assertEqual(facts.module_effects()["productivity-module"], (-0.05, 0.04))
        self.assertEqual(facts.module_effects()["speed-module-3"], (0.5, 0.0))
        self.assertEqual(facts.module_slots()["assembling-machine-3"], 4)
        self.assertNotIn("assembling-machine-1", facts.module_slots())
        self.assertIn("iron-plate", facts.productive())
        self.assertNotIn("iron-chest", facts.productive())

    def test_electric_consumers(self):
        self.assertTrue(facts.electric_consumer("programmable-speaker"))
        self.assertTrue(facts.electric_consumer("decider-combinator"))
        for name in ("power-switch", "display-panel", "accumulator", "solar-panel", "steam-engine",
                     "constant-combinator", "stone-furnace"):
            self.assertFalse(facts.electric_consumer(name), name)

    def test_signals(self):
        sig = facts.signals()
        self.assertIn("iron-plate", sig["item"])
        self.assertIn("water", sig["fluid"])
        self.assertIn("signal-A", sig["virtual"])
        self.assertIn("legendary", sig["quality"])
        self.assertIn("iron-gear-wheel", sig["recipe"])
        self.assertIn("assembling-machine-1", sig["entity"])
        never = facts.never_transmit()["virtual"]
        for name in ("signal-everything", "signal-anything", "signal-each"):
            self.assertIn(name, never)
            self.assertNotIn(name, sig["virtual"])
        # the codec's hand-copied list is all the game's
        self.assertEqual(sorted(set(codec.VIRTUAL_SIGNALS) - set(sig["virtual"]) - set(never)), [])

    def test_wire_connectors(self):
        ids = facts.load()["circuit"]["connector_ids"]
        self.assertIn("power_switch_left_copper", ids["5"])
        self.assertEqual(ids["6"], ["power_switch_right_copper"])
        self.assertEqual(facts.wire_reach(), 9.0)


class WideCatalogTest(unittest.TestCase):
    def test_new_entities(self):
        for name, size in (("power-switch", (2, 2)), ("programmable-speaker", (1, 1)),
                           ("display-panel", (1, 1)), ("train-stop", (2, 2)),
                           ("decider-combinator", (1, 2)), ("rocket-silo", (9, 9))):
            self.assertEqual(CAT.size(name), size, name)
        self.assertEqual(CAT.entity("power-switch")["circuit"]["connectors"], [1, 2, 5, 6])
        self.assertEqual(CAT.entity("decider-combinator")["circuit"]["connectors"], [1, 2, 3, 4])
        self.assertEqual(CAT.entity("small-lamp")["energy"]["source"], "electric")

    def test_every_row_has_the_new_fields(self):
        for row in CAT._entities.values():
            for key in ("placed_by", "energy", "circuit"):
                self.assertIn(key, row, row["name"])

    def test_row_values(self):
        self.assertEqual(CAT.entity("electric-energy-interface")["collision_box"],
                         [-0.8984375, -0.8984375, 0.8984375, 0.8984375])
        self.assertEqual(CAT.entity("inserter")["rotation_speed"], 0.014)

    def test_items_are_what_places_an_entity(self):
        self.assertTrue(CAT.is_item("rail"))
        self.assertFalse(CAT.is_item("straight-rail"))
        self.assertTrue(CAT.is_item("power-switch"))

    def test_is_electric(self):
        self.assertTrue(CAT.is_electric("programmable-speaker"))
        self.assertFalse(CAT.is_electric("power-switch"))
        self.assertFalse(CAT.is_electric("display-panel"))
        self.assertFalse(CAT.is_electric("accumulator"))
        with self.assertRaises(KeyError):
            CAT.is_electric("no-such-thing")


class AdoptedDictsTest(unittest.TestCase):
    """The dicts are the game's (docs/RELEASE-2.1.1.md lists what 2.1.1's first commit kept)."""

    def test_catalog_dicts(self):
        self.assertEqual(catalog.FUEL_USE_W, facts.burns("chemical"))
        for name, w in (("stone-furnace", 90e3), ("steel-furnace", 90e3),
                        ("burner-mining-drill", 150e3), ("boiler", 1.8e6),
                        ("burner-inserter", 144e3), ("heating-tower", 40e6)):
            self.assertEqual(catalog.FUEL_USE_W[name], w, name)
        self.assertNotIn("biochamber", catalog.FUEL_USE_W)
        for name, j in (("coal", 4e6), ("wood", 2e6), ("solid-fuel", 12e6), ("rocket-fuel", 100e6),
                        ("nuclear-fuel", 1.21e9), ("carbon", 2e6)):
            self.assertEqual(catalog.FUEL_VALUE_J[name], j, name)
        self.assertNotIn("uranium-fuel-cell", catalog.FUEL_VALUE_J)
        self.assertEqual(catalog.MINING_TIME["uranium-ore"], 2.0)
        self.assertEqual(catalog.MINING_TIME["tungsten-ore"], 5.0)
        self.assertNotIn("crude-oil", catalog.MINING_TIME)
        self.assertEqual(catalog.STEAM_PER_S, {"boiler": 60.0, "steam-engine": 30.0,
                                               "heat-exchanger": 10e6 / (485 * 200.0),
                                               "steam-turbine": 60.0})
        self.assertEqual(catalog.HEAT_W, {"nuclear-reactor": 40e6, "heat-exchanger": 10e6,
                                          "heating-tower": 40e6})
        self.assertEqual(catalog.REACTOR_FUEL_S, {"uranium-fuel-cell": 200.0})
        self.assertEqual(catalog.MINING_RADIUS, {"electric-mining-drill": 2.49,
                                                 "burner-mining-drill": 0.99,
                                                 "big-mining-drill": 6.49, "pumpjack": 0.49})
        self.assertEqual(catalog.CIRCUIT_WIRE_REACH, 9.0)

    def test_templates_dicts(self):
        self.assertEqual(templates.MODULE_SLOTS["assembling-machine-3"], 4)
        self.assertEqual(templates.MODULE_SLOTS["lab"], 2)
        self.assertEqual(templates.MODULE_SLOTS["foundry"], 4)
        self.assertEqual(len(templates.MODULE_SLOTS), 19)
        self.assertEqual(templates.MODULE_EFFECTS["productivity-module-3"], (-0.15, 0.10))
        self.assertEqual(templates.MODULE_EFFECTS["efficiency-module"], (0.0, 0.0))
        self.assertEqual(templates.MODULE_EFFECTS["quality-module"], (-0.05, 0.0))

    def test_productive(self):
        self.assertEqual(elaborate.PRODUCTIVE, facts.productive())
        self.assertIn("rocket-part", elaborate.PRODUCTIVE)
        self.assertIn("casting-iron", elaborate.PRODUCTIVE)
        self.assertNotIn("iron-chest", elaborate.PRODUCTIVE)

    def test_is_electric(self):
        self.assertFalse(CAT.is_electric("biochamber"))
        self.assertFalse(CAT.is_electric("captive-biter-spawner"))
        self.assertTrue(CAT.is_electric("railgun-turret"))

    def test_a_drill_mines_its_categories(self):
        self.assertTrue(facts.mines("electric-mining-drill", "calcite"))
        self.assertFalse(facts.mines("electric-mining-drill", "tungsten-ore"))
        self.assertTrue(facts.mines("big-mining-drill", "tungsten-ore"))
        with self.assertRaises(templates.TemplateError):
            templates.miner_row({"n": 1, "resource": "tungsten-ore"}, CAT)
        got = templates.miner_row({"n": 1, "resource": "tungsten-ore", "drill": "big-mining-drill"},
                                  CAT)
        self.assertEqual(got[0].makes, {"tungsten-ore": 2.5 / 5.0})

    def test_circuit_reach(self):
        self.assertEqual(CAT.circuit_reach("big-electric-pole"), 32.0)
        self.assertEqual(CAT.circuit_reach("small-electric-pole"), 7.5)
        self.assertEqual(CAT.circuit_reach("power-switch"), 10.0)
        self.assertEqual(CAT.circuit_reach("inserter"), 9.0)
        self.assertEqual(CAT.circuit_reach("pipe"), 9.0)          # no connector: the usual


if __name__ == "__main__":
    unittest.main()
