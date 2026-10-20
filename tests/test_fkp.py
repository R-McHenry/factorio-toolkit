import unittest

from fkcore import codec, compose, fkp
from fkcore.catalog import Catalog

CAT = Catalog.load()

# A 7x7 factory: two gear assemblers fed from an iron belt along the top, an underground pair, a
# splitter and an output belt, all in the factory's own frame. Hand-written, canonical.
MINI = """\
fkp 1 factory mini
size 7x7
inst gears AsmRow machine=assembling-machine-1 n=2 recipe=iron-gear-wheel at 0,2 rot 0 sig 0123456789
cover power power pole=small-electric-pole
e gears/i0 fast-inserter 1.5,1.5 S net=iron
e gears/i1 fast-inserter 4.5,1.5 S net=iron
e gears/m0 assembling-machine-1 1.5,3.5 recipe=iron-gear-wheel
e gears/m1 assembling-machine-1 4.5,3.5 recipe=iron-gear-wheel
e gears/o0 fast-inserter 1.5,5.5 S net=gear
e gears/o1 fast-inserter 4.5,5.5 S net=gear
e power/p0 small-electric-pole 3.5,1.5
e ~gear/b0 transport-belt 1.5,6.5 E net=gear
e ~gear/b1 transport-belt 2.5,6.5 E net=gear
e ~gear/b2 transport-belt 3.5,6.5 E net=gear
e ~gear/b3 transport-belt 4.5,6.5 E net=gear
e ~gear/s0 splitter 5.5,6 E net=gear
e ~iron/b0 transport-belt 0.5,0.5 E net=iron
e ~iron/b1 transport-belt 1.5,0.5 E net=iron
e ~iron/b2 transport-belt 4.5,0.5 E net=iron
e ~iron/b3 transport-belt 5.5,0.5 E net=iron
e ~iron/b10 transport-belt 6.5,0.5 S net=iron
e ~iron/u0 underground-belt 2.5,0.5 E net=iron ug=in
e ~iron/u1 underground-belt 3.5,0.5 E net=iron ug=out
"""

SURFACE = """\
fkp 1 surface nauvis
cover robots robots
plot mini at 10,0 rot 0 size 7x7
plot turned at 20,0 rot 1 size 7x7
claim boom-test box -10,0 -5,5 until 4500000 "explosives trial"
mark Rory_618@4512000 tiles 3,4 3,5 until 4620000
e robots/r0 roboport 2,10
"""


def surface_with(text=SURFACE, factories=None):
    lay = fkp.loads(text)
    mini = fkp.loads(MINI)
    turned = fkp.loads(MINI.replace("factory mini", "factory turned"))
    return compose.compose(lay, factories or {"mini": mini, "turned": turned}, CAT)


class FormatTest(unittest.TestCase):
    def test_canonical_round_trip(self):
        for text in (MINI, SURFACE):
            lay = fkp.loads(text)
            self.assertEqual(fkp.dumps(lay, CAT), text)
            self.assertEqual(fkp.loads(fkp.dumps(lay)), lay)

    def test_canonical_order_and_comments(self):
        messy = "# hand edit\n" + "\n".join(reversed(MINI.splitlines()[2:])) + "\n"
        messy = MINI.splitlines()[0] + "\n" + MINI.splitlines()[1] + "  # the frame\n" + messy
        self.assertEqual(fkp.dumps(fkp.loads(messy)), MINI)

    def test_parse_errors_name_the_line(self):
        for text, msg in (("fkp 2 factory x\n", "first line"),
                          ("fkp 1 factory x\ne a/b transport-belt 1,1 E net=x\n"
                           "e a/b transport-belt 2,1 E net=x\n", "duplicate key"),
                          ("fkp 1 factory x\nwire a b\n", "unknown line"),
                          ("fkp 1 factory x\nplot a at 0,0 rot 0 size 2x2\n", "surfaces only"),
                          ("fkp 1 factory x\ne a/b transport-belt 1;1 E\n", "expected x,y")):
            with self.assertRaises(fkp.FkpError) as cm:
                fkp.loads(text, "t.fkp")
            self.assertIn(msg, str(cm.exception))
            self.assertIn("t.fkp:", str(cm.exception))


class BlueprintRoundTripTest(unittest.TestCase):
    def test_fkp_blueprint_fkp_is_identical(self):
        for text in (MINI, SURFACE):
            bp = codec.fkp_to_blueprint(fkp.loads(text))
            back = codec.blueprint_to_fkp(bp)
            self.assertEqual(fkp.dumps(back), text)
            self.assertEqual(codec.fkp_to_blueprint(back), bp)       # deterministic

    def test_game_fields(self):
        rows, desc = codec.read_blueprint(codec.fkp_to_blueprint(fkp.loads(MINI)))
        doc = {r["src"]: r for r in rows}
        self.assertEqual(doc["~iron/u0"]["attrs"], {"net": "iron", "ug": "in"})
        self.assertIsNone(doc["power/p0"]["direction"])
        self.assertEqual(doc["gears/o0"]["direction"], 8)
        self.assertTrue(desc.startswith("fkp 1 factory mini\nsize 7x7\ninst gears"))
        # the game's own fields, for the paste
        import base64, json, zlib
        bp = codec.fkp_to_blueprint(fkp.loads(MINI))
        ents = {e["tags"]["src"]: e for e in
                json.loads(zlib.decompress(base64.b64decode(bp[1:])))["blueprint"]["entities"]}
        self.assertEqual(ents["~iron/u1"]["type"], "output")
        self.assertEqual(ents["gears/m0"]["recipe"], "iron-gear-wheel")
        self.assertNotIn("direction", ents["power/p0"])

    def test_composed_rows_round_trip(self):
        s = surface_with()
        rows, _desc = codec.read_blueprint(codec.blueprint(s.rows()))
        self.assertEqual(rows, s.rows())


class InvariantTest(unittest.TestCase):
    def refused(self, text):
        with self.assertRaises(fkp.InvariantError) as cm:
            fkp.dumps(fkp.loads(text), CAT)
        return "\n".join(cm.exception.problems)

    def test_two_entities_on_a_tile(self):
        msg = self.refused(MINI + "e ~iron/b99 transport-belt 2.5,3.5 N net=iron\n")
        self.assertIn("~iron/b99: tile 2,3 is already gears/m0", msg)

    def test_carrier_nets(self):
        self.assertIn("carries no net", self.refused(MINI.replace(
            "e ~iron/b0 transport-belt 0.5,0.5 E net=iron", "e ~iron/b0 transport-belt 0.5,0.5 E")))
        self.assertIn("carries two nets", self.refused(MINI.replace(
            "0.5,0.5 E net=iron", "0.5,0.5 E net=iron,gear")))

    def test_owner_must_resolve(self):
        msg = self.refused(MINI + "e ghost/b0 transport-belt 0.5,4.5 E net=iron\n"
                                  "e ~copper/b0 transport-belt 0.5,5.5 E net=iron\n")
        self.assertIn("ghost/b0: owner ghost is not an inst or cover line", msg)
        self.assertIn("~copper/b0: owner ~copper is not a net of this factory", msg)

    def test_outside_the_frame(self):
        self.assertIn("outside the factory's 7x7 frame",
                      self.refused(MINI + "e ~iron/b20 transport-belt 7.5,0.5 E net=iron\n"))

    def test_a_good_layout_writes(self):
        self.assertEqual(fkp.invariants(fkp.loads(MINI), CAT), [])


class ComposeTest(unittest.TestCase):
    def test_keys_and_plots(self):
        s = surface_with()
        self.assertEqual(s.problems, [])
        self.assertEqual(len(s.entities), 2 * 19 + 1)
        e = s.entities["nauvis:mini/gears/m0"]
        self.assertEqual((e.x, e.y, e.plot), (11.5, 3.5, "mini"))
        self.assertIn("nauvis:robots/r0", s.entities)

    def test_rotation(self):
        s = surface_with()
        # rot 1: the frame's top row (iron belt, flowing east) becomes its right column, flowing
        # south; the frame's top-left corner lands on the right, and the plot origin stays put.
        b0 = s.entities["nauvis:turned/~iron/b0"]
        self.assertEqual((b0.x, b0.y, b0.dir), (26.5, 0.5, 8))
        s0 = s.entities["nauvis:turned/~gear/s0"]
        self.assertEqual((s0.x, s0.y, s0.dir), (21, 5.5, 8))       # a 1x2 splitter turns 2x1
        self.assertEqual(s0.tiles, ((20, 5), (21, 5)))
        turned = [t for k, e in s.entities.items() if k.startswith("nauvis:turned/")
                  for t in e.tiles]
        self.assertEqual((min(t[0] for t in turned), min(t[1] for t in turned)), (20, 0))
        self.assertEqual((max(t[0] for t in turned), max(t[1] for t in turned)), (26, 6))

    def test_four_turns_are_the_identity(self):
        mini = fkp.loads(MINI)
        for key, e in mini.entities.items():
            x, y, d = float(e.x), float(e.y), e.dir
            for _ in range(4):
                x, y, d = compose.turn(x, y, d, 1, (7, 7))
            self.assertEqual((x, y, d), (e.x, e.y, e.dir), key)

    def test_every_rotation_keeps_footprints_in_the_plot(self):
        for rot in range(4):
            text = f"fkp 1 surface s\nplot mini at 3,-4 rot {rot} size 7x7\n"
            s = compose.compose(fkp.loads(text), {"mini": fkp.loads(MINI)}, CAT)
            self.assertEqual(s.problems, [], rot)
            # 2 machines x 9 + 4 inserters + 1 pole + 9 belts + 2 undergrounds + a 2-tile splitter
            self.assertEqual(len(s.tiles), 36, rot)

    def test_overlapping_plots_are_refused(self):
        s = surface_with(SURFACE.replace("plot turned at 20,0", "plot turned at 15,3"))
        self.assertIn("plots mini and turned overlap", s.problems)
        self.assertTrue(any("is already nauvis:mini/" in p for p in s.problems))

    def test_plot_problems(self):
        s = surface_with(SURFACE.replace("size 7x7\nplot turned", "size 6x7\nplot turned")
                         + "e robots/r1 roboport 12,4\n")
        self.assertIn("plot mini: the factory (7x7 turned) does not fit 6x7", s.problems)
        self.assertIn("nauvis:robots/r1: shared infrastructure inside plot mini", s.problems)
        s = surface_with(factories={"mini": fkp.loads(MINI)})
        self.assertIn("plot turned: no factory layout called turned", s.problems)

    def test_whose(self):
        s = surface_with()
        self.assertEqual(s.whose(11, 3), ("entity", {"key": "nauvis:mini/gears/m0",
                                                     "name": "assembling-machine-1", "net": None,
                                                     "plot": "mini"}))
        self.assertEqual(s.whose(10, 0)[1]["net"], "iron")
        self.assertEqual(s.whose(16, 3), ("plot", {"plot": "mini"}))
        self.assertEqual(s.whose(-8, 2), ("claim", {"key": "nauvis:claim/boom-test",
                                                    "reason": "explosives trial"}))
        self.assertEqual(s.whose(3, 5), ("mark", {"key": "nauvis:mark/Rory_618@4512000"}))
        self.assertEqual(s.whose(50, 50), ("sanctioned", {}))

    def test_render(self):
        s = surface_with()
        art = compose.render(s, CAT, (10, 0, 17, 7))
        self.assertEqual(art.splitlines(), [
            ">>uU>>v",
            ".i.+i..",
            "AAAAAA.",
            "AAAAAA.",
            "AAAAAA.",
            ".i..iS.",
            ".>>>>S.",
        ])


if __name__ == "__main__":
    unittest.main()
