"""The fluid boxes as read from the game (fkcore/data/fluidboxes.json, Catalog.fluid_boxes_at).

The MEASURED cases are what the game reported for entities created on the lab surface
(LuaFluidBox.get_pipe_connections: position and target_position), 2026-10-20, 2.0.77.
"""
import unittest

from fkcore.catalog import Catalog

CAT = Catalog.load()

#: (name, x, y, direction) -> [[(flow, position, target_position), ...] per live box] (measured)
MEASURED = {
    ("chemical-plant", 758.5, 420.5, 4): [
        [("input", (759.5, 419.5), (760.5, 419.5))], [("input", (759.5, 421.5), (760.5, 421.5))],
        [("output", (757.5, 419.5), (756.5, 419.5))], [("output", (757.5, 421.5), (756.5, 421.5))]],
    ("oil-refinery", 766.5, 428.5, 8): [
        [("input", (767.5, 426.5), (767.5, 425.5))], [("input", (765.5, 426.5), (765.5, 425.5))],
        [("output", (768.5, 430.5), (768.5, 431.5))], [("output", (766.5, 430.5), (766.5, 431.5))],
        [("output", (764.5, 430.5), (764.5, 431.5))]],
    ("boiler", 759, 452.5, 4): [
        [("input-output", (758.5, 451.5), (758.5, 450.5)),
         ("input-output", (758.5, 453.5), (758.5, 454.5))],
        [("output", (759.5, 452.5), (760.5, 452.5))]],
    ("pump", 759, 476.5, 4): [[("output", (759.5, 476.5), (760.5, 476.5)),
                               ("input", (758.5, 476.5), (757.5, 476.5))]],
    ("offshore-pump", 774.5, 524.5, 12): [[("output", (774.5, 524.5), (775.5, 524.5))]],
    ("pumpjack", 766.5, 532.5, 8): [[("output", (765.5, 533.5), (765.5, 534.5))]],
}


def tile(v):
    return int(v // 1)


class FluidBoxTest(unittest.TestCase):
    def test_read_from_the_game(self):
        data = CAT._fluid
        self.assertEqual(data["version"], "2.0.77")
        self.assertIn("RCON", data["source"])
        for name in ("offshore-pump", "boiler", "steam-engine", "chemical-plant", "oil-refinery",
                     "pumpjack", "storage-tank", "pump", "pipe", "pipe-to-ground"):
            self.assertTrue(CAT.has_fluid_boxes(name), name)
        self.assertFalse(CAT.has_fluid_boxes("assembling-machine-1"))

    def test_the_measured_connections(self):
        for (name, x, y, d), boxes in MEASURED.items():
            got = CAT.fluid_boxes_at(name, x, y, d)
            self.assertEqual(len(got), len(boxes), name)
            for b, want in zip(got, boxes):
                self.assertEqual(len(b.conns), len(want), name)
                for c, (flow_, pos, target) in zip(b.conns, want):
                    self.assertEqual((c.flow, c.tile, c.target),
                                     (flow_, (tile(pos[0]), tile(pos[1])),
                                      (tile(target[0]), tile(target[1]))), (name, d))

    def test_a_boiler_and_an_engine(self):
        water, steam = CAT.fluid_boxes_at("boiler", 1.5, 1, 0)
        self.assertEqual((water.fluid, steam.fluid), ("water", "steam"))
        self.assertEqual([(c.tile, c.dir, c.target) for c in water.conns],
                         [((0, 1), 12, (-1, 1)), ((2, 1), 4, (3, 1))])     # both on its south row
        self.assertEqual([(c.tile, c.target) for c in steam.conns], [((1, 0), (1, -1))])
        (engine,) = CAT.fluid_boxes_at("steam-engine", 1.5, 2.5, 0)
        self.assertEqual([c.target for c in engine.conns], [(1, 5), (1, -1)])

    def test_the_recipe_makes_the_boxes(self):
        water, gas = CAT.fluid_boxes_at("chemical-plant", 1.5, 1.5, 0, "sulfur")
        self.assertEqual((water.fluid, [c.target for c in water.conns]), ("water", [(0, -1)]))
        self.assertEqual((gas.fluid, [c.target for c in gas.conns]), ("petroleum-gas", [(2, -1)]))
        (plastic,) = CAT.fluid_boxes_at("chemical-plant", 1.5, 1.5, 0, "plastic-bar")
        self.assertEqual(len(plastic.conns), 2)       # one fluid on a side: both inputs, one box
        crude, gas = CAT.fluid_boxes_at("oil-refinery", 2.5, 2.5, 0, "basic-oil-processing")
        self.assertEqual([c.target for c in crude.conns + gas.conns], [(3, 5), (4, -1)])
        self.assertEqual(len(CAT.fluid_boxes_at("chemical-plant", 1.5, 1.5, 0)), 4)
        self.assertEqual(CAT.fluid_boxes_at("assembling-machine-2", 1.5, 1.5, 0), [])
        (conc,) = CAT.fluid_boxes_at("assembling-machine-2", 1.5, 1.5, 0, "concrete")
        self.assertEqual(conc.fluid, "water")

    def test_pipe_to_ground_and_the_infinity_pipe(self):
        (b,) = CAT.fluid_boxes_at("pipe-to-ground", 0.5, 0.5, 12)
        normal, under = b.conns
        self.assertEqual((normal.dir, normal.target, under.type, under.dir, under.reach),
                         (12, (-1, 0), "underground", 4, 10))
        self.assertEqual((CAT.kind("infinity-pipe"), CAT.size("infinity-pipe")),
                         ("infinity-pipe", (1, 1)))
        self.assertEqual(sorted(CAT.water_tiles("offshore-pump", 10.5, 10.5, 0)),
                         [(9, 8), (9, 9), (10, 8), (10, 9), (11, 8), (11, 9)])


if __name__ == "__main__":
    unittest.main()
