import unittest

from fkcore import surface

# CORE-V1.md §11, as written there
NAUVIS = """
# nauvis.surface.fk
surface nauvis
mode     play                                       # fair play on: attention-scoped, notify nearby
terrain  map
catalog  base

place plant = reactor-w3   plot -10,-10 20x20       # standalone: its own grid (a Literal)
place boot  = boot         plot 30,10 20x12  temporary until main.running
place main  = main         plot 10,40 120x80        # the monolith, ore to science
place ammo  = iron-ammo    plot 140,20 16x12 patch iron-ore#2   # standalone, in a hurry

robots main: cover main, boot
claim boom-test box -20,40 -10,50 until 4500000 "explosives trial"

watch plots:      keep
watch sanctioned: mark 2h
notify            nearby

target automation-science-pack 10/min, logistic-science-pack 10/min
"""


class SurfaceFileTest(unittest.TestCase):
    def test_core_v1_example(self):
        sf = surface.loads(NAUVIS, "nauvis.surface")
        self.assertEqual((sf.name, sf.mode, sf.terrain, sf.notify_mode), ("nauvis", "play", "map",
                                                                         "nearby"))
        self.assertEqual(list(sf.places), ["plant", "boot", "main", "ammo"])
        self.assertEqual(sf.places["boot"].lifecycle, "temporary until main.running")
        self.assertEqual(sf.places["ammo"].patch, "iron-ore#2")
        self.assertEqual((sf.places["main"].x, sf.places["main"].w), (10, 120))
        self.assertEqual(sf.robots, {"main": ["main", "boot"]})
        self.assertEqual(sf.claims["boom-test"].reason, "explosives trial")
        self.assertEqual(sf.watch, {"plots": "keep", "sanctioned": "mark 2h"})
        self.assertAlmostEqual(sf.targets["logistic-science-pack"], 10 / 60)

    def test_floorplan(self):
        sf = surface.loads(NAUVIS.replace("temporary until main.running", "retired"))
        lay = surface.floorplan(sf)
        self.assertEqual(sorted(lay.plots), ["ammo", "main", "plant"])     # retired frees its plot
        self.assertEqual(lay.plots["ammo"].params, {"module": "iron-ammo", "patch": "iron-ore#2"})
        self.assertIn("boom-test", lay.claims)

    def test_lab_defaults_to_notify_all(self):
        self.assertEqual(surface.loads("surface lab\nmode lab\n").notify_mode, "all")

    def test_errors(self):
        for text, msg in (("mode play\n", "no surface line"),
                          ("surface s\nmode war\n", "mode is play or lab"),
                          ("surface s\nplace a = a plot 1,2 3y4\n", "expected WxH"),
                          ("surface s\nfly away\n", "unknown line"),
                          ("surface s\nplace a = a plot 0,0 2x2\nplace a = b plot 5,5 2x2\n",
                           "placed twice")):
            with self.assertRaises(surface.SurfaceError) as cm:
                surface.loads(text, "t.surface")
            self.assertIn(msg, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
