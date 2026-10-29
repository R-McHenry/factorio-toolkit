"""2.0.53: advanced oil's three fluids on three nets without `items`, electric furnaces in a
SmelterRow, `modules=` on machines and rows, and the furnace column of the player's own cells."""
import json
import os
import unittest

from fkcore import codec, connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, elaborate_file

CAT = Catalog.load()
EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples")

OIL = """
crude  = InfinityPipe<fluid=crude-oil, rate=20/s>     @(4, 0)
water  = InfinityPipe<fluid=water, rate=40/s>         @(12, 0)
ref    = Refinery<recipe=advanced-oil-processing>     @(6, 4, rot 2)
hcrack = ChemPlant<recipe=heavy-oil-cracking>         @(2, 16)
lcrack = ChemPlant<recipe=light-oil-cracking>         @(10, 24)
sulf   = ChemPlant<recipe=sulfur>                     @(26, 24)
net crude: crude -> ref
net wat:   water -> ref, hcrack, lcrack, sulf
net heavy: ref -> hcrack
net light: ref, hcrack -> lcrack
net gas:   ref, lcrack -> sulf
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def codes(flat):
    return sorted({c.code for c in flat.checks})


class AdvancedOilTest(unittest.TestCase):
    def test_each_fluid_on_the_net_that_takes_it(self):
        flat = flat_of(OIL)
        self.assertEqual(flat.nets["heavy"].items, ["heavy-oil"])
        self.assertEqual(flat.nets["light"].items, ["light-oil"])
        self.assertEqual(flat.nets["gas"].items, ["petroleum-gas"])
        for code in ("two-nets", "SUSHI_SINK", "CLOG"):
            self.assertNotIn(code, codes(flat))

    def test_it_routes(self):
        flat = flat_of(OIL)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual({n for n, x in rep.nets.items() if x.status != "connected"}, set())

    def test_one_fluid_drivers_are_as_before(self):
        flat = flat_of("""
            water = InfinityPipe<fluid=water, rate=40/s> @(0, 0)
            gas   = InfinityPipe<fluid=petroleum-gas, rate=40/s> @(0, 8)
            chem  = ChemPlant<recipe=sulfur> @(8, 4)
            net w: water -> chem
            net g: gas -> chem
        """)
        self.assertEqual((flat.nets["w"].items, flat.nets["g"].items), (["water"], ["petroleum-gas"]))

    def test_a_net_into_nothing_that_takes_a_fluid_keeps_them_all(self):
        flat = flat_of("""
            ref = Refinery<recipe=advanced-oil-processing> @(0, 0)
            box = Chest<provider> @(10, 0)
            net all: ref -> box
        """)
        self.assertEqual(flat.nets["all"].items, ["heavy-oil", "light-oil", "petroleum-gas"])


class ElectricFurnaceRowTest(unittest.TestCase):
    TEXT = """
        smelt = SmelterRow<n=6, recipe=iron-plate, machine=electric-furnace{mods}> @(10, 12)
        ore   = Chest<requester, item=iron-ore, rate=3/s> @(2, 12)
        box   = Chest<provider> @(4, 22)
        net o: ore -> smelt
        net p: smelt -> box
    """

    def layout(self, mods=""):
        flat = flat_of(self.TEXT.format(mods=mods))
        lay, _notes = expand.expand_factory(flat, CAT)
        self.assertEqual(fkp.invariants(lay, CAT), [])
        return flat, lay

    def test_three_tiles_a_furnace_and_no_fuel(self):
        flat, lay = self.layout()
        xs = sorted(e.x for k, e in lay.entities.items() if e.name == "electric-furnace")
        self.assertEqual([b - a for a, b in zip(xs, xs[1:])], [3.0] * 5)
        self.assertEqual(sorted(flat.machines["smelt/m0"].needs), ["iron-ore"])

    def test_modules_go_in_the_paste(self):
        _flat, lay = self.layout(", modules=productivity-module")
        e = lay.entities["smelt/m0"]
        bp = json.loads(e.attrs["config"])
        self.assertEqual(bp["items"], [{"id": {"name": "productivity-module", "quality": "normal"},
                                        "items": {"in_inventory": [
                                            {"count": 1, "inventory": 4, "stack": 0},
                                            {"count": 1, "inventory": 4, "stack": 1}]}}])
        rows, _ = codec.read_blueprint(codec.fkp_to_blueprint(lay))
        self.assertTrue(any(r["name"] == "electric-furnace" for r in rows))


class ModulesTest(unittest.TestCase):
    def test_speed_and_productivity_change_the_rates(self):
        plain = flat_of("a = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-2>")
        fast = flat_of("a = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-2, "
                       "modules=speed-module>")
        prod = flat_of("a = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-2, "
                       "modules=productivity-module|productivity-module>")
        base = plain.machines["a/m0"]
        self.assertAlmostEqual(fast.machines["a/m0"].makes["iron-gear-wheel"],
                               base.makes["iron-gear-wheel"] * 1.4)
        self.assertAlmostEqual(prod.machines["a/m0"].needs["iron-plate"],
                               base.needs["iron-plate"] * 0.9)
        self.assertAlmostEqual(prod.machines["a/m0"].makes["iron-gear-wheel"],
                               base.makes["iron-gear-wheel"] * 0.9 * 1.08)

    def test_a_single_machine_gets_the_requests(self):
        flat = flat_of("a = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-2, "
                       "modules=speed-module|efficiency-module> @(0, 0)")
        lay, _notes = expand.expand_factory(flat, CAT)
        items = json.loads(lay.entities["a/m0"].attrs["config"])["items"]
        self.assertEqual([(i["id"]["name"], i["items"]["in_inventory"][0]["stack"]) for i in items],
                         [("speed-module", 0), ("efficiency-module", 1)])

    def test_refused(self):
        for text, why in (
                ("a = AsmRow<n=2, recipe=iron-gear-wheel, modules=speed-module>", "no module slots"),
                ("a = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-2, "
                 "modules=speed-module|speed-module|speed-module>", "has 2 slots"),
                ("a = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-2, "
                 "modules=gear>", "not a module")):
            with self.assertRaises(Exception) as ctx:
                flat_of(text)
            self.assertIn(why, str(ctx.exception))


class FurnaceColumnTest(unittest.TestCase):
    def test_the_example_routes(self):
        flat = elaborate_file(os.path.join(EXAMPLES, "furnace-column.fk"), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
        self.assertEqual({n for n, x in rep.nets.items() if x.status != "connected"}, set())
        self.assertEqual(sum(1 for e in r.layout.entities.values()
                             if e.name == "electric-furnace"), 8)


if __name__ == "__main__":
    unittest.main()
