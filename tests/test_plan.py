"""fk plan, the forward ratio calculator (Rory, 2026-10-21: can an agent easily work out how many
miners 15 blue science assemblers need?), against numbers worked by hand."""
import contextlib
import importlib.util
import io
import os
import re
import unittest

from fkcore import __main__ as cli, plan
from fkcore.catalog import Catalog

CAT = Catalog.load()
ROOT = os.path.join(os.path.dirname(__file__), "..")
FUEL = 90e3 / 4e6                                  # coal/s a stone furnace burns


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class FifteenBlueTest(unittest.TestCase):
    """15 assembling-machine-2 on chemical-science-pack (2 packs in 24 s at speed 0.75) make
    0.9375 packs/s: 0.46875 crafts/s take 0.46875 sulfur, 1.40625 advanced circuits and 0.9375
    engines a second. Engines (10 s, 0.075/s each): 12.5 assemblers, 0.9375 steel and gears, 1.875
    pipes. Advanced circuits (6 s, 0.125/s each): 11.25 assemblers, 2.8125 plastic, 5.625 cable,
    2.8125 green circuits, which take 2.8125 iron and 8.4375 cable. Cable 14.0625/s is 7.03125
    copper. Iron: steel 4.6875 + gears 1.875 + pipes 1.875 + circuits 2.8125 = 11.25/s, 36 stone
    furnaces (0.3125/s each), and 15 more for steel (16 s each). Drills at 0.5/s: 22.5 on iron ore,
    14.0625 on copper. Plastic: 1.40625 chemical plants, 1.40625 coal and 28.125 petroleum gas a
    second; sulfur 7.03125 gas and as much water. Gas 35.15625/s from basic oil processing (9/s a
    refinery) is 3.90625 refineries and 78.125 crude oil. Fuel: 73.5 furnaces x 0.0225 coal/s."""

    def setUp(self):
        self.p = plan.plan(CAT, "chemical-science-pack", machines=15)

    def machines(self, item, machine, n):
        row = self.p.row(item)
        self.assertEqual(row.machine, machine, item)
        self.assertAlmostEqual(row.machines, n, places=9, msg=item)

    def test_the_packs_and_what_goes_into_them(self):
        self.assertAlmostEqual(self.p.rate, 0.9375)
        asm = "assembling-machine-2"
        for item, machine, n in (
                ("chemical-science-pack", asm, 15), ("engine-unit", asm, 12.5),
                ("advanced-circuit", asm, 11.25), ("electronic-circuit", asm, 1.875),
                ("iron-gear-wheel", asm, 0.625), ("pipe", asm, 1.25), ("copper-cable", asm, 4.6875),
                ("sulfur", "chemical-plant", 0.234375), ("plastic-bar", "chemical-plant", 1.40625),
                ("petroleum-gas", "oil-refinery", 3.90625)):
            self.machines(item, machine, n)
        self.assertAlmostEqual(self.p.row("plastic-bar").rate, 2.8125)
        self.assertAlmostEqual(self.p.row("sulfur").rate, 0.46875)
        self.assertEqual(self.p.row("petroleum-gas").recipe, "basic-oil-processing")

    def test_the_plates_and_their_furnaces(self):
        iron = self.p.row("iron-plate")
        self.assertAlmostEqual(iron.rate, 11.25)
        self.machines("iron-plate", "stone-furnace", 36)
        self.machines("steel-plate", "stone-furnace", 15)
        self.machines("copper-plate", "stone-furnace", 22.5)
        self.assertAlmostEqual(self.p.row("copper-plate").rate, 7.03125)
        for who, rate in (("steel-plate", 4.6875), ("electronic-circuit", 2.8125),
                          ("iron-gear-wheel", 1.875), ("pipe", 1.875)):
            self.assertAlmostEqual(iron.takers[who], rate, msg=who)

    def test_the_raw_inputs(self):
        self.machines("iron-ore", "electric-mining-drill", 22.5)
        self.machines("copper-ore", "electric-mining-drill", 14.0625)
        coal = self.p.row("coal")
        self.assertAlmostEqual(coal.takers["plastic-bar"], 1.40625)
        self.assertAlmostEqual(coal.takers["furnace fuel"], 73.5 * FUEL)
        self.assertAlmostEqual(coal.machines, (1.40625 + 73.5 * FUEL) / 0.5)
        self.assertAlmostEqual(self.p.row("crude-oil").rate, 78.125)
        self.assertAlmostEqual(self.p.row("crude-oil").machines, 7.8125)
        self.assertAlmostEqual(self.p.row("water").rate, 7.03125)
        self.assertTrue(any("basic-oil-processing" in n for n in self.p.notes))

    def test_consumers_come_before_their_makers(self):
        items = [r.item for r in self.p.rows]
        self.assertEqual(items[0], "chemical-science-pack")
        for r in self.p.rows:
            for who in r.takers:
                if who in items:
                    self.assertLess(items.index(who), items.index(r.item), (who, r.item))
        self.assertEqual([r.item for r in self.p.rows if r.recipe is None],
                         ["iron-ore", "copper-ore", "coal", "crude-oil", "water"])

    def test_whole_machines_round_up(self):
        self.assertEqual([plan._build(n) for n in (12.5, 15.000000000000002, 36.0, 0.23, 0.0)],
                         [13, 15, 36, 1, 0])


class RateTest(unittest.TestCase):
    def test_units(self):
        for text, rate in (("1/s", 1.0), ("60/min", 1.0), ("3600/h", 1.0), ("2", 2.0),
                           (" 30/min ", 0.5)):
            self.assertAlmostEqual(plan.parse_rate(text), rate, msg=text)
        for text in ("1/day", "0", "-1/s", "x/s", "nan", "inf/s", ""):
            with self.assertRaises(plan.PlanError, msg=text):
                plan.parse_rate(text)

    def test_a_rate_scales_the_machines_plan(self):
        by_rate = plan.plan(CAT, "chemical-science-pack", rate=1.0)
        by_machines = plan.plan(CAT, "chemical-science-pack", machines=15)
        self.assertEqual([r.item for r in by_rate.rows], [r.item for r in by_machines.rows])
        for a, b in zip(by_rate.rows, by_machines.rows):
            self.assertAlmostEqual(a.rate, b.rate / 0.9375, msg=a.item)
            self.assertAlmostEqual(a.machines, b.machines / 0.9375, msg=a.item)
        self.assertAlmostEqual(by_rate.row("chemical-science-pack").machines, 16)

    def test_machines_of_a_raw_input_are_its_drills(self):
        p = plan.plan(CAT, "iron-ore", machines=10, mining_productivity=2)
        self.assertAlmostEqual(p.rate, 10 * 0.5 * 1.2)
        self.assertEqual([r.item for r in p.rows], ["iron-ore"])


class OptionsTest(unittest.TestCase):
    def test_assembling_machine_3(self):
        p = plan.plan(CAT, "chemical-science-pack", machines=15, asm="assembling-machine-3")
        self.assertAlmostEqual(p.rate, 15 * 1.25 / 24 * 2)              # 1.5625 packs/s
        self.assertAlmostEqual(p.row("engine-unit").machines, 12.5)     # same speed, same ratio
        self.assertAlmostEqual(p.row("iron-plate").machines, 36 * 1.5625 / 0.9375)

    def test_steel_furnaces_halve_the_furnaces_and_their_fuel(self):
        p = plan.plan(CAT, "chemical-science-pack", machines=15, furnace="steel-furnace")
        for item, n in (("iron-plate", 18), ("steel-plate", 7.5), ("copper-plate", 11.25)):
            self.assertEqual(p.row(item).machine, "steel-furnace")
            self.assertAlmostEqual(p.row(item).machines, n, msg=item)
        self.assertAlmostEqual(p.row("coal").takers["furnace fuel"], 36.75 * FUEL)

    def test_electric_furnaces_burn_no_coal(self):
        p = plan.plan(CAT, "chemical-science-pack", machines=15, furnace="electric-furnace")
        coal = p.row("coal").takers
        self.assertEqual(set(coal), {"plastic-bar"})
        self.assertAlmostEqual(coal["plastic-bar"], 1.40625)

    def test_mining_productivity(self):
        p = plan.plan(CAT, "chemical-science-pack", machines=15, mining_productivity=2)
        self.assertAlmostEqual(p.row("iron-ore").machines, 22.5 / 1.2)
        self.assertAlmostEqual(p.row("copper-ore").machines, 14.0625 / 1.2)
        self.assertAlmostEqual(p.row("crude-oil").machines, 7.8125 / 1.2)
        self.assertAlmostEqual(p.drill, 0.6)

    def test_assembling_machine_1_takes_no_fluid(self):
        # concrete: 10 from 5 bricks, 1 iron ore and 100 water in 10 s, with fluid
        p = plan.plan(CAT, "concrete", rate=1.0, asm="assembling-machine-1")
        self.assertEqual(p.row("concrete").machine, "assembling-machine-2")
        self.assertAlmostEqual(p.row("concrete").machines, 1 / (10 * 0.75 / 10))
        self.assertTrue(any("assembling-machine-1 takes no fluid" in n for n in p.notes))
        self.assertAlmostEqual(p.row("stone").rate, 1.0)                # 0.5 bricks/s, 2 stone each


class OilTest(unittest.TestCase):
    """rocket-fuel 0.1/s: 2 assembling-machine-2 (15 s at 0.75), 1 solid fuel and 1 light oil a
    second. Solid fuel from petroleum gas (20 gas, 1 s): one chemical plant, 20 gas/s. A refinery
    on advanced oil processing (5 s) makes 11 gas, 9 light and 5 heavy oil a second from 20 crude
    and 10 water; on basic, 9 gas from 20 crude."""

    def test_advanced_oil_processing_makes_gas_and_light_oil_in_one_group(self):
        p = plan.plan(CAT, "rocket-fuel", rate=0.1,
                      recipes={"petroleum-gas": "advanced-oil-processing"})
        self.assertAlmostEqual(p.row("rocket-fuel").machines, 2)
        self.assertEqual(p.row("solid-fuel").recipe, "solid-fuel-from-petroleum-gas")
        gas, light = p.row("petroleum-gas"), p.row("light-oil")
        self.assertAlmostEqual(gas.machines, 20 / 11)                    # the gas binds
        self.assertTrue(light.shared)
        self.assertIsNone(light.machines)
        self.assertAlmostEqual(gas.surplus["light-oil"], 20 / 11 * 9 - 1)
        self.assertAlmostEqual(gas.surplus["heavy-oil"], 20 / 11 * 5)
        self.assertAlmostEqual(p.row("crude-oil").rate, 20 / 11 * 20)
        self.assertAlmostEqual(p.row("water").rate, 20 / 11 * 10)
        self.assertTrue(any("without cracking" in n for n in p.notes))
        self.assertTrue(any(n.startswith("solid-fuel: planned with") for n in p.notes))

    def test_a_byproduct_is_never_credited_to_another_recipe(self):
        p = plan.plan(CAT, "rocket-fuel", rate=0.1)
        self.assertEqual(p.row("petroleum-gas").recipe, "basic-oil-processing")
        self.assertAlmostEqual(p.row("petroleum-gas").machines, 20 / 9)
        light = p.row("light-oil")
        self.assertEqual(light.recipe, "advanced-oil-processing")
        self.assertAlmostEqual(light.machines, 1 / 9)
        self.assertAlmostEqual(light.surplus["petroleum-gas"], 11 / 9)
        self.assertAlmostEqual(p.row("crude-oil").rate, (20 / 9 + 1 / 9) * 20)

    def test_a_recipe_nets_what_it_makes_for_itself(self):
        # coal liquefaction: 10 coal, 25 heavy oil and 50 steam -> 90 heavy, 20 light, 10 gas
        p = plan.plan(CAT, "lubricant", rate=10, recipes={"heavy-oil": "coal-liquefaction"})
        heavy = p.row("heavy-oil")
        self.assertAlmostEqual(heavy.machines, 10 / 13)                  # 65 net a 5 s craft
        self.assertAlmostEqual(p.row("coal").rate, 10 / 13 * 2)
        self.assertEqual(p.row("steam").machine, "boiler")
        self.assertAlmostEqual(p.row("steam").machines, 10 / 13 * 10 / 60)
        self.assertEqual(set(heavy.takers), {"lubricant"})            # not its own refineries

    def test_petroleum_gas_given(self):
        p = plan.plan(CAT, "chemical-science-pack", machines=15, raw=["petroleum-gas"])
        gas = p.row("petroleum-gas")
        self.assertIsNone(gas.recipe)
        self.assertAlmostEqual(gas.rate, 35.15625)
        self.assertNotIn("crude-oil", [r.item for r in p.rows])
        self.assertTrue(any("petroleum-gas is a raw input" in n for n in p.notes))


class InputsTest(unittest.TestCase):
    def test_raw_items_stop_the_tree(self):
        p = plan.plan(CAT, "chemical-science-pack", machines=15, raw=["iron-plate", "copper-plate"])
        items = [r.item for r in p.rows]
        self.assertNotIn("iron-ore", items)
        self.assertNotIn("copper-ore", items)
        self.assertEqual((p.row("iron-plate").source, p.row("iron-plate").machines),
                         ("given (--raw)", None))
        self.assertAlmostEqual(p.row("iron-plate").rate, 11.25)
        self.assertAlmostEqual(p.row("coal").takers["furnace fuel"], 15 * FUEL)   # steel only

    def test_mistakes_are_one_plan_error(self):
        cases = [dict(item="chemical-sience-pack", rate=1.0),
                 dict(item="iron-plate", rate=1.0, machines=2),
                 dict(item="iron-plate"),
                 dict(item="iron-plate", machines=0),
                 dict(item="iron-plate", rate=1.0, asm="assembling-machine-9"),
                 dict(item="iron-plate", rate=1.0, mining_productivity=-1),
                 dict(item="iron-plate", rate=1.0, recipes={"iron-plate": "casting-iron"}),
                 dict(item="iron-plate", rate=1.0, recipes={"iron-plate": "copper-plate"}),
                 dict(item="iron-plate", rate=1.0, recipes={"iron-plate": "nope"}),
                 dict(item="water", rate=1.0, recipes={"water": "empty-water-barrel"}),
                 dict(item="iron-plate", machines=2, raw=["iron-plate"])]
        for kw in cases:
            with self.assertRaises(plan.PlanError, msg=kw):
                plan.plan(CAT, **kw)
        with self.assertRaisesRegex(plan.PlanError, "did you mean chemical-science-pack"):
            plan.plan(CAT, "chemical-sience-pack", rate=1.0)
        with self.assertRaisesRegex(plan.PlanError, "water -> water-barrel -> water"):
            plan.plan(CAT, "water", rate=1.0, recipes={"water": "empty-water-barrel"})
        self.assertEqual(plan.parse_recipes("a=b, c = d"), {"a": "b", "c": "d"})
        with self.assertRaises(plan.PlanError):
            plan.parse_recipes("iron-plate")


class CommandTest(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["plan", *argv])
        return code, out.getvalue(), err.getvalue()

    def line(self, text, item):
        found = [ln for ln in text.splitlines() if ln.split()[:1] == [item]]
        self.assertEqual(len(found), 1, item)
        return found[0].split()

    def test_fifteen_blue_assemblers_in_one_call(self):
        code, text, _err = self.run_cli("chemical-science-pack", "--machines", "15")
        self.assertEqual(code, 0)
        self.assertIn("plan chemical-science-pack 0.938/s (56.25/min), what 15 "
                      "assembling-machine-2 make", text)
        for item, numbers in (("engine-unit", ["12.50", "13"]),
                              ("advanced-circuit", ["11.25", "12"]),
                              ("iron-plate", ["11.250", "36.00", "36"]),
                              ("steel-plate", ["15.00", "15"]),
                              ("copper-plate", ["7.031", "22.50", "23"]),
                              ("plastic-bar", ["2.812"]), ("sulfur", ["0.469"]),
                              ("iron-ore", ["11.250", "22.50", "23"]),
                              ("copper-ore", ["7.031", "14.06", "15"])):
            words = self.line(text, item)
            for n in numbers:
                self.assertIn(n, words, item)
        self.assertRegex(text, r"for furnace fuel 1\.654, plastic-bar 1\.406")
        self.assertIn("oil: petroleum-gas from basic-oil-processing", text)

    def test_a_rate_and_the_options(self):
        code, text, _err = self.run_cli("chemical-science-pack", "60/min", "--asm",
                                        "assembling-machine-3", "--furnace", "electric-furnace",
                                        "--mining-productivity", "1", "--recipe",
                                        "petroleum-gas=advanced-oil-processing")
        self.assertEqual(code, 0)
        self.assertIn("plan chemical-science-pack 1.000/s (60.00/min)", text)
        self.assertEqual(self.line(text, "chemical-science-pack")[-2:], ["9.60", "10"])
        self.assertIn("electric-furnace", self.line(text, "iron-plate"))
        self.assertIn("advanced-oil-processing", self.line(text, "petroleum-gas"))
        surplus = [ln for ln in text.splitlines() if ln.strip().startswith("surplus ")]
        self.assertEqual(len(surplus), 1)
        self.assertRegex(surplus[0], r"light-oil [\d.]+, heavy-oil [\d.]+ \(/s\)")

    def test_a_mistake_is_one_line(self):
        code, text, err = self.run_cli("chemical-sience-pack", "1/s")
        self.assertEqual((code, text), (2, ""))
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("did you mean chemical-science-pack", err)

    def test_fk_plan_runs_here(self):
        spec = importlib.util.spec_from_file_location("fk_agent_plan",
                                                      os.path.join(ROOT, "agent", "fk.py"))
        fk_agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fk_agent)
        self.assertIn("plan", fk_agent.LOCAL)
        self.assertNotIn("plan", fk_agent.HOST)

    def test_the_player_hears_of_it(self):
        toolkit = read("agent", "docs", "TOOLKIT.md")
        self.assertIn("## How many machines and drills for a rate", toolkit)
        self.assertIn("fk plan chemical-science-pack --machines 15", toolkit)
        brief = read("agent", "prompts", "core-v1.md")
        unstuck = brief.split("## Ways to get unstuck", 1)[1].split("\n## ", 1)[0]
        self.assertTrue(re.search(r"`fk plan [^`]+`", unstuck), unstuck)


if __name__ == "__main__":
    unittest.main()
