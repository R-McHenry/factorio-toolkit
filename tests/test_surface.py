import unittest

from fkcore import surface

# CORE-V1.md §11, as written there
NAUVIS = """
# nauvis.surface.fk
surface nauvis
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
        self.assertEqual((sf.name, sf.free, sf.force_name, sf.terrain, sf.notify_mode),
                         ("nauvis", False, "player", "map", "nearby"))
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

    def test_a_free_surface_defaults_to_notify_all(self):
        # 3.1: `free` is a property; the lab's surface file says it, and its force
        sf = surface.loads("surface lab\nfree\nforce lab\n")
        self.assertEqual((sf.free, sf.force_name, sf.notify_mode, sf.notes), (True, "lab", "all", []))
        self.assertEqual(surface.loads("surface s\nfree no\n").free, False)
        self.assertEqual(surface.loads("surface s\nfree yes\nnotify off\n").notify_mode, "off")

    def test_an_old_mode_line_still_reads_for_one_release(self):
        # mode lab implied free, force lab and notify all; mode play implied nothing
        sf = surface.loads("surface lab\nmode lab\n")
        self.assertEqual((sf.free, sf.force_name, sf.notify_mode), (True, "lab", "all"))
        self.assertEqual(len(sf.notes), 1)
        self.assertIn("fk migrate-surface", sf.notes[0])
        sf = surface.loads("surface lab\nforce v2lab\nmode lab\n")        # an own force stays
        self.assertEqual(sf.force_name, "v2lab")
        sf = surface.loads("surface nauvis\nmode play\n")
        self.assertEqual((sf.free, sf.force_name, len(sf.notes)), (False, "player", 1))

    def test_an_old_mode_line_migrates_to_the_properties(self):
        text = "# the lab\nsurface  lab\nmode     lab\nterrain  none\n\nplace a = a plot 0,0 4x4\n"
        now, mode = surface.migrate_mode(text)
        self.assertEqual(mode, "lab")
        self.assertNotIn("mode     lab", now.replace("# (3.1) `mode lab`", ""))
        sf = surface.loads(now)
        self.assertEqual((sf.free, sf.force_name, sf.notes, list(sf.places)),
                         (True, "lab", [], ["a"]))
        self.assertEqual(now.splitlines()[:5], ["# the lab", "surface  lab",
                                               surface.MODE_NOTE.format(
                                                   mode="lab", what=": free, and the paste's force"),
                                               "free", "force    lab"])
        # a force line of its own is kept, and mode play leaves only the note
        now, _m = surface.migrate_mode("surface lab\nforce v2lab\nmode lab\n")
        self.assertEqual(surface.loads(now).force_name, "v2lab")
        self.assertNotIn("force    lab", now)
        now, mode = surface.migrate_mode("surface n\nmode play\nterrain map\n")
        self.assertEqual((mode, surface.loads(now).free, surface.loads(now).notes), ("play", False, []))
        self.assertEqual(surface.migrate_mode("surface n\nterrain map\n"),
                         ("surface n\nterrain map\n", None))

    def test_load_game_takes_the_surface_that_is_not_free(self):
        import os
        import shutil
        import tempfile
        d = tempfile.mkdtemp(prefix="fksurf-")
        self.addCleanup(shutil.rmtree, d, True)
        for name, text in (("lab.surface", "surface lab\nfree\nforce lab\n"),
                           ("nauvis.surface", "surface nauvis\nterrain none\n")):
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        self.assertEqual(surface.load_game(d).name, "nauvis")

    def test_properties_are_what_a_module_alone_copies(self):
        sf = surface.loads("surface lab\nfree\nforce lab\nterrain none\ncatalog base\nnotify all\n"
                           "watch sanctioned: mark 2h\nplace a = a plot 0,0 4x4\nremind 20s\n")
        self.assertEqual(surface.properties(sf).splitlines(),
                         ["surface  lab", "free", "force    lab", "terrain  none", "catalog  base",
                          "notify   all", "remind   20s", "watch sanctioned: mark 2h"])

    def test_remind_is_the_alert_reminder_cadence(self):
        sf = surface.loads("surface lab\nremind 20s   # a short one, for a test\n")
        self.assertEqual((sf.remind, sf.remind_ticks), ("20s", 1200))
        default = surface.loads("surface nauvis\n")
        self.assertEqual((default.remind, default.remind_ticks), ("10min", 36000))  # open
        for bad in ("remind soon\n", "remind 0s\n", "remind 1 min\n"):
            with self.assertRaises(surface.SurfaceError):
                surface.loads("surface s\n" + bad)

    def test_errors(self):
        for text, msg in (("terrain map\n", "no surface line"),
                          ("surface s\nmode war\n", "mode is gone"),
                          ("surface s\nfree maybe\n", "free, or free yes|no"),
                          ("surface s\nplace a = a plot 1,2 3y4\n", "expected WxH"),
                          ("surface s\nfly away\n", "unknown line"),
                          ("surface s\nremind soon\n", "malformed remind line"),
                          ("surface s\nplace a = a plot 0,0 2x2\nplace a = b plot 5,5 2x2\n",
                           "placed twice")):
            with self.assertRaises(surface.SurfaceError) as cm:
                surface.loads(text, "t.surface")
            self.assertIn(msg, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
