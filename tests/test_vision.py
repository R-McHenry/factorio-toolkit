"""fkcore.vision (2.1): zoom, layers and images of `fk look`, against fixture captures and fake
game reads (no game)."""
import json
import os
import struct
import tempfile
import unittest
import zlib
from unittest import mock

from fkcore import link, look, scene, vision
from fkcore.png import Canvas
from tests import test_look as _tl
from tests.test_look import AREA, CAT, belt, capture, ug

HERE = os.path.dirname(__file__)
GOLDEN = os.path.join(HERE, "data", "vision", "look-z1-2.0.78.json")


def row(n, t, x, y, d=0, g=False, force="lab", w=1, h=1, **kw):
    out = {"n": n, "t": t, "x": x, "y": y, "d": d, "g": g, "force": force,
           "box": [x - w / 2 + 0.1, y - h / 2 + 0.1, x + w / 2 - 0.1, y + h / 2 - 0.1]}
    out.update(kw)
    return out


def sc(*rows, area=(0, 0, 64, 64)):
    return scene.from_capture({"tick": 1, "area": list(area), "things": list(rows)})


def lines_of(lay_name, raw, live=None, design=None, zoom=1, area=(0, 0, 64, 64), tags=None):
    frame = vision.Frame(area, zoom)
    facts = vision.facts_from_read(raw, live) if raw is not None else None
    text, _ = vision.compose_view(vision.View(zoom, (lay_name,)), frame, CAT, design_sc=design,
                                  live_sc=live, live=facts, plots=(tags or ([], []))[0],
                                  tags=tags)
    return text


def panel(text, title, side="live"):
    """The rows of one panel: {y: row} of its live (or design) side."""
    start = next(k for k, ln in enumerate(text) if ln.startswith(title))
    two = " | " in text[start + 1]
    out = {}
    for ln in text[start + 1:]:
        if not ln[:5].strip().lstrip("-").isdigit():
            break
        body = ln[6:]
        if two:
            d, lv = body.split(" | ")
            body = lv if side == "live" else d
        out[int(ln[:5])] = body
    return out


class _OnLabSense(unittest.TestCase):
    """test_look's game (games/lab-sense) and its fixture captures, without its tests."""
    setUp = _tl.LookTest.setUp
    tearDown = _tl.LookTest.tearDown
    run_look = _tl.LookTest.run_look


class ZoomOneTest(_OnLabSense):
    """Zoom 1 with no layer: 2.0.78's look, byte for byte, over the fixture captures."""

    def test_zoom_one_is_2_0_78_byte_for_byte(self):
        with open(GOLDEN, encoding="utf-8") as fh:
            golden = json.load(fh)
        pol = look.policy(self.sf)
        cases = {
            "applied": [],
            "foreign": self.foreign,
            "undergrounds": [ug(306.5, 447.5, "input"), ug(310.5, 447.5, "output"),
                             ug(316.5, 446.5, "input"), ug(320.5, 446.5, "input"),
                             ug(326.5, 445.5, "output", ghost=True)],
            "ghost-and-turned": [belt(307.5, 430.5, d=0), belt(308.5, 430.5, d=8)],
        }
        self.assertEqual(set(cases), set(golden))
        for name, extra in cases.items():
            live = scene.from_capture(capture(self.s, extra=extra))
            for view in (None, vision.View(), vision.View(1, (), None)):
                lk = look.report(self.s, live, CAT, AREA, pol, view=view)
                self.assertEqual(lk.lines(), golden[name], (name, view))

    def test_run_with_a_plain_view_reads_nothing_more(self):
        r, lk = self.run_look()
        with mock.patch.object(link, "vision_read") as vr:
            r2, lk2 = self.run_look(view=vision.View())
        vr.assert_not_called()
        self.assertEqual(lk.lines(), lk2.lines())

    def test_zoom_one_layers_keep_the_plain_render_first(self):
        live = scene.from_capture(capture(self.s))
        pol = look.policy(self.sf)
        plain = look.report(self.s, live, CAT, AREA, pol).lines()
        tags = vision.design_tags(self.dir, self.sf, self.s)
        lk = look.report(self.s, live, CAT, AREA, pol, view=vision.View(1, ("tags",)),
                         facts=vision.facts_from_read({}, live, tags[0]), tags=tags)
        got = lk.lines()
        base = [ln for ln in plain if ln.startswith("render:") or ln[:5].strip().isdigit()]
        at = got.index(base[0])
        self.assertEqual(got[at:at + len(base)], base)
        self.assertTrue(any(ln.startswith("layer tags: design | live") for ln in got))


class CellTest(unittest.TestCase):
    def test_a_machine_wins_over_belts_and_poles(self):
        self.assertEqual(vision.decide({"A": 1, ">": 9, "+": 3}), "A")
        self.assertEqual(vision.decide({"F": 2, "A": 2}), "A")        # a tie: the fixed order
        self.assertEqual(vision.decide({"F": 3, "A": 2}), "F")        # else the commonest

    def test_a_mostly_belt_cell_shows_its_flow(self):
        self.assertEqual(vision.decide({">": 3, "v": 1, "i": 2, "+": 1}), ">")
        self.assertEqual(vision.decide({">": 1, "C": 1, "i": 3}), "C")   # not mostly belt
        self.assertEqual(vision.decide({">": 1, "i": 3}), ">")           # then belt over inserter
        self.assertEqual(vision.decide({"+": 1}), "+")
        self.assertEqual(vision.decide({}), ".")

    def test_cells_count_every_cell_a_thing_touches(self):
        live = sc(row("assembling-machine-2", "assembling-machine", 3.5, 3.5, w=3, h=3),
                  *[row("transport-belt", "transport-belt", x + 0.5, 8.5, d=4) for x in range(8)],
                  row("small-electric-pole", "electric-pole", 7.5, 1.5),
                  row("biter-spawner", "unit-spawner", 20, 20, force="enemy", w=5, h=5))
        frame = vision.Frame((0, 0, 16, 16), 4)
        cells = vision.scene_cells(live, frame)
        self.assertEqual(cells[(0, 0)], {"A": 1})
        self.assertEqual(cells[(1, 1)], {"A": 1})
        self.assertEqual(cells[(1, 0)], {"A": 1, "+": 1})
        self.assertEqual(cells[(0, 2)], {">": 4})
        grid = vision.grid_rows(frame, vision.base_grid(frame, CAT, sc=live))
        self.assertEqual(grid, ["AA..", "AA..", ">>..", "...."])

    def test_the_game_reads_the_same_classes(self):
        cfg = vision.read_config("lab", "lab", vision.Frame((0, 0, 64, 64), 8), ("power",),
                                 False, [("iron", 0, 0, 32, 32, "iron")], True,
                                 link.SKIP_TYPES)
        self.assertEqual(cfg["classes"]["names"]["chemical-plant"], "H")
        self.assertEqual(cfg["classes"]["types"]["land-mine"], "")
        self.assertEqual(cfg["chunks"], [[0, 0], [1, 0], [0, 1], [1, 1]])
        self.assertTrue(cfg["want"]["cells"] and cfg["want"]["power"])
        self.assertFalse(cfg["want"]["robots"])
        for t, c in vision._TYPE_CLASS.items():
            self.assertEqual(vision.cell_class(t, "x", 4), ">" if c == "belt" else c)

    def test_counts_from_the_game_render_as_the_scene_does(self):
        live = sc(row("assembling-machine-2", "assembling-machine", 3.5, 3.5, w=3, h=3),
                  *[row("transport-belt", "transport-belt", 9.5, y + 0.5, d=8) for y in range(16)])
        frame = vision.Frame((0, 0, 16, 16), 8)
        cells = {f"{k[0]},{k[1]}": v for k, v in vision.scene_cells(live, frame).items()}
        facts = vision.facts_from_read({"cells": cells})
        self.assertEqual(vision.base_grid(frame, CAT, cells=facts.cells),
                         vision.base_grid(frame, CAT, sc=live))

    def test_plots_from_zoom_eight_are_outlines_with_names_and_machines(self):
        things = [row("assembling-machine-2", "assembling-machine", 3.5 + 3 * k, 3.5, w=3, h=3)
                  for k in range(6)]
        live = sc(*things, area=(0, 0, 64, 32))
        plots = [("smelters", 0, 0, 40, 24, "smelt")]
        frame = vision.Frame((0, 0, 64, 32), 8)
        facts = vision.facts_from_read({}, live, plots)
        text, _ = vision.compose_view(vision.View(8), frame, CAT, live_sc=live, live=facts,
                                      plots=plots, tags=(plots, []))
        rows = panel(text, "render:")
        self.assertEqual(rows[0], "*sme*...")              # the name as far as it fits
        self.assertEqual(rows[8], "|...|...")
        self.assertEqual(rows[16], "*---*...")
        self.assertIn("plot smelters: 6 machine(s), at 0,0 40x24", text)

    def test_parse_layers(self):
        self.assertEqual(vision.parse_layers("all"), vision.LAYERS)
        self.assertEqual(vision.parse_layers("tags,robots"), ("robots", "tags"))
        self.assertEqual(vision.parse_layers(""), ())
        with self.assertRaises(ValueError):
            vision.parse_layers("trains")

    def test_map_mode(self):
        self.assertTrue(vision.map_mode((0, 0, 64, 64), 8))
        self.assertFalse(vision.map_mode((0, 0, 64, 64), 4))
        self.assertTrue(vision.map_mode((0, 0, 512, 512), 2))
        self.assertFalse(vision.map_mode((0, 0, 512, 512), 1))


class LayerTest(unittest.TestCase):
    def test_robots(self):
        raw = {"roboports": [[10, 10, "roboport", 4, 8, 7, 3, 1, 0, 0],
                             [50, 10, "roboport", 4, 8, 9, 0, 2, 1, 0]],
               "networks": {"7": [5, 2, 4, 3], "9": [0, 0, 2, 2]},
               "ghosts": [[12.5, 12.5, "wooden-chest"], [30.5, 30.5, "wooden-chest"]],
               "nghosts": 2}
        text = lines_of("robots", raw, live=sc())
        rows = panel(text, "layer robots")
        self.assertEqual(rows[10][6:15], "11111111,")      # network 7's logistic area: key 1
        self.assertEqual(rows[10][2:5], ",,,")             # construction only
        self.assertEqual(rows[10][46:54], "22222222")      # network 9: key 2
        self.assertEqual(rows[30][30], "!")                # a ghost outside every construction area
        self.assertEqual(rows[12][12], "1")                # the other ghost is covered
        self.assertIn("robots 1: logistic network 7, 1 roboport(s); logistic robots 5 (3 busy, "
                      "2 idle, 2 in flight), construction 4 (1 busy, 3 idle, 3 in flight); "
                      "docked 3 logistic, 1 construction; charging 0, waiting to charge 0", text)
        self.assertTrue(any(ln.startswith("robots: ! 1 ghost(s) outside every construction "
                                          "area") and "30.5,30.5" in ln for ln in text))

    def test_robots_in_the_design(self):
        design = sc(row("roboport", "roboport", 10, 10, w=4, h=4),
                    row("roboport", "roboport", 40, 10, w=4, h=4),
                    row("roboport", "roboport", 200, 10, w=4, h=4))
        facts = vision.facts_from_design(design, CAT)
        self.assertEqual([r["net"] for r in facts.roboports], [1, 1, 2])     # 30 < 25 + 25
        text = lines_of("robots", None, design=design)
        self.assertIn("robots 1: logistic network 1, 2 roboport(s)", text)

    def test_power(self):
        raw = {"poles": [[5.5, 5.5, "small-electric-pole", 2.5, 3],
                         [30.5, 5.5, "small-electric-pole", 2.5, 8]],
               "machines": [[5.5, 9.5, "assembling-machine-2", "assembling-machine", 0,
                             "no_power", "iron-gear-wheel", 3],
                            [30.5, 9.5, "assembling-machine-2", "assembling-machine", 0,
                             "low_power", "", 8]],
               "switches": [[18, 5, False]]}
        live = sc(row("small-electric-pole", "electric-pole", 5.5, 5.5),
                  row("small-electric-pole", "electric-pole", 30.5, 5.5),
                  row("assembling-machine-2", "assembling-machine", 5.5, 9.5, w=3, h=3),
                  row("assembling-machine-2", "assembling-machine", 30.5, 9.5, w=3, h=3))
        text = lines_of("power", raw, live=live)
        rows = panel(text, "layer power")
        self.assertEqual(rows[5][2:9], ".11+11.")           # supply 2.5: tiles 3..7
        self.assertEqual(rows[5][28:33], "22+22")
        self.assertEqual(rows[9][5], "X")
        self.assertEqual(rows[9][30], "~")
        self.assertEqual(rows[5][18], "/")
        self.assertIn("power 1: electric network 3, 1 pole(s), 1 machine(s) in its supply area",
                      text)
        self.assertIn("power: switch 18,5 off (open) ($ on, / off)", text)
        self.assertTrue(any(ln.startswith("power: X no_power 1: assembling-machine-2 5.5,9.5")
                            for ln in text))

    def test_power_in_the_design_wire_components(self):
        design = sc(row("medium-electric-pole", "electric-pole", 0.5, 0.5),
                    row("medium-electric-pole", "electric-pole", 8.5, 0.5),
                    row("medium-electric-pole", "electric-pole", 30.5, 0.5))
        facts = vision.facts_from_design(design, CAT)
        self.assertEqual([p["net"] for p in facts.poles], [1, 1, 2])       # reach 9

    def test_defense(self):
        raw = {"turrets": [[10, 10, "gun-turret", "ammo-turret", 18,
                            {"firearm-magazine": 20}],
                           [40, 10, "gun-turret", "ammo-turret", 18, {}],
                           [10, 40, "laser-turret", "electric-turret", 24, []]],
               "mines": [[20.5, 20.5]],
               "walls": [[10.5, 25.5, "wall"], [10.5, 29.5, "wall"], [60.5, 60.5, "gate"]],
               "nests": [[60, 30, "biter-spawner", "unit-spawner"],
                         [55.5, 50.5, "small-worm-turret", "turret"]]}
        text = lines_of("defense", raw, live=sc())
        rows = panel(text, "layer defense")
        self.assertEqual(rows[10][10], "T")
        self.assertEqual(rows[10][40], "0")                  # EMPTY
        self.assertEqual(rows[10][20], "g")
        self.assertEqual(rows[25][10], "#")                  # within 18 of the first turret
        self.assertEqual(rows[29][10], "#")                  # in the laser's range
        self.assertEqual(rows[60][60], "!")                  # a gap
        self.assertEqual(rows[20][20], "x")
        self.assertEqual(rows[30][60], "@")
        self.assertEqual(rows[50][55], "w")
        self.assertEqual(rows[25][15], "*")                  # gun and laser
        self.assertIn("defense g: 2 gun-turret (gun), range 18; ammo firearm-magazine 20; 1 "
                      "EMPTY (0)", text)
        self.assertIn("defense: # 2 wall(s), G 1 gate(s); ! 1 of them outside every turret's "
                      "range (a gap in the ring)", text)

    def test_defense_in_the_design(self):
        design = sc(row("gun-turret", "ammo-turret", 10, 10, w=2, h=2))
        text = lines_of("defense", None, design=design)
        rows = panel(text, "layer defense", "design")
        self.assertEqual(rows[10][27], "g")                  # 18 tiles east
        self.assertEqual(rows[10][29], ".")

    def test_pollution(self):
        raw = {"pollution": [[0, 0, 15.0, 0], [1, 0, 250.0, 0], [0, 1, 0.0, 0], [1, 1, 40.0, 1]],
               "nests": [[50, 50, "biter-spawner", "unit-spawner"]]}
        text = lines_of("pollution", raw, live=sc(), zoom=8)
        rows = panel(text, "layer pollution")
        self.assertEqual(rows[0], "11113333")
        self.assertEqual(rows[32], "....2222")
        self.assertEqual(rows[48][6], "!")
        self.assertIn("pollution: ! reaches a nest in chunk 1,1 (40.0, 1 nest(s))", text)

    def test_pipes(self):
        raw = {"pipes": [[x + 0.5, 5.5, "pipe", "pipe", 0, 11, "water", 50, 100]
                         for x in range(4)]
               + [[6, 5.5, "pump", "pump", 4, 12, "", 0, 200]]
               + [[x + 0.5, 5.5, "pipe", "pipe", 0, 13, "crude-oil", 10, 100]
                  for x in range(8, 10)],
               "opens": [[20.5, 20.5, "chemical-plant", 2]]}
        text = lines_of("pipes", raw, live=sc())
        rows = panel(text, "layer pipes")
        self.assertEqual(rows[5][:11], "aaaa.PP.ee.")      # the pump is a segment of its own
        self.assertEqual(rows[20][20], "!")
        self.assertIn("pipes a: water, 50% full, 200/400 (4 pipe(s), 0 tank(s) K, 0 pump(s) P)",
                      text)
        self.assertIn("pipes e: crude-oil, 10% full, 20/200 (2 pipe(s), 0 tank(s) K, 0 pump(s) "
                      "P)", text)
        self.assertTrue(any(ln.startswith("pipes: ! 1 machine(s) with a fluid connection")
                            for ln in text))

    def test_recipes(self):
        raw = {"machines": [[5.5, 5.5, "assembling-machine-2", "assembling-machine", 0,
                             "working", "iron-gear-wheel", 1],
                            [15.5, 5.5, "assembling-machine-2", "assembling-machine", 0,
                             "no_ingredients", "electronic-circuit", 1]]}
        live = sc(row("assembling-machine-2", "assembling-machine", 5.5, 5.5, w=3, h=3),
                  row("assembling-machine-2", "assembling-machine", 15.5, 5.5, w=3, h=3))
        design = sc(row("assembling-machine-2", "assembling-machine", 5.5, 5.5, w=3, h=3,
                        rc="iron-gear-wheel"))
        text = lines_of("recipes", raw, live=live, design=design)
        rows = panel(text, "layer recipes")
        self.assertEqual(rows[4][4:7], "gea")
        self.assertEqual(rows[5][4:7], "***")
        self.assertEqual(rows[4][14:17], "cir")
        self.assertEqual(rows[6][14:17], "nnn")
        self.assertEqual(panel(text, "layer recipes", "design")[4][4:7], "gea")
        self.assertIn("recipes gear (iron-gear-wheel): 1 machine(s) (1 working)", text)
        self.assertIn("recipes circ (electronic-circuit): 1 machine(s) (1 no_ingredients)", text)
        z4 = lines_of("recipes", raw, live=live, design=design, zoom=4)
        rows = panel(z4, "layer recipes")
        self.assertEqual(rows[4][1], "2")                    # gear: key 2 on both sides
        self.assertEqual(panel(z4, "layer recipes", "design")[4][1], "2")
        self.assertEqual(rows[4][3], "!")                    # circ: not working
        self.assertEqual(vision.recipe_tag("iron-gear-wheel"), "gear")
        self.assertEqual(vision.recipe_tag("rocket-part"), "rprt")

    def test_tags(self):
        plots = [("iron", 0, 0, 20, 12, "smelt")]
        insts = [("iron/row", "SmelterRow", 2, 2, 10, 6)]
        design = sc(row("stone-furnace", "furnace", 3, 3, w=2, h=2))
        text = lines_of("tags", None, design=design, tags=(plots, insts))
        rows = panel(text, "layer tags", "design")
        self.assertEqual(rows[0][:21], "*------------------*.")
        self.assertEqual(rows[2][:4], "|.aF")                # the letter on its corner
        self.assertEqual(rows[3][4], "a")
        self.assertIn("tags a: instance iron/row (SmelterRow) at 2,2 8x4", text)
        self.assertIn("tags: plot iron (smelt) at 0,0 20x12", text)

    def test_a_layer_the_design_doesnt_know_draws_live_only(self):
        text = lines_of("pollution", {"pollution": [[0, 0, 5.0, 0]]}, live=sc(), design=sc())
        self.assertTrue(any(ln.startswith("layer pollution: live,") for ln in text))


class FairPlayTest(unittest.TestCase):
    def test_uncharted_chunks_are_blank_and_never_differ(self):
        live = sc(row("assembling-machine-2", "assembling-machine", 5.5, 5.5, w=3, h=3),
                  row("assembling-machine-2", "assembling-machine", 40.5, 5.5, w=3, h=3))
        cells = {f"{k[0]},{k[1]}": v
                 for k, v in vision.scene_cells(live, vision.Frame((0, 0, 64, 32), 8)).items()
                 if k[0] < 4}
        facts = vision.facts_from_read({"cells": cells, "dark": [[1, 0]]})
        text, _ = vision.compose_view(vision.View(8), vision.Frame((0, 0, 64, 32), 8), CAT,
                                      design_sc=live, live=facts)
        rows = panel(text, "render:")
        self.assertEqual(rows[0], "A...    ")
        self.assertIn("0 cells differ", text[0])
        self.assertIn("(blank) uncharted", text[-1])

    def test_the_read_skips_uncharted_chunks_in_play_mode(self):
        cfg = vision.read_config("nauvis", "player", vision.Frame((0, 0, 64, 32), 8), (), True,
                                 (), True, link.SKIP_TYPES)
        lua = link.lua_vision(cfg, "t")
        self.assertIn("if cfg.play and not f.is_chunk_charted(s, {cx, cy}) then", lua)
        self.assertTrue(cfg["play"])


class ReadTest(unittest.TestCase):
    def test_the_read_is_read_only(self):
        cfg = vision.read_config("lab", "lab", vision.Frame((0, 0, 64, 64), 8), vision.LAYERS,
                                 False, (), True, link.SKIP_TYPES)
        for lua in (link.lua_vision(cfg, "t"), link.lua_vision_wide(cfg, "t")):
            for word in ("on_event", "add_command", "create_entity", "destroy", "insert{",
                         "insert_fluid",
                         "set_", "order_", "revive", "rcon.print(helpers.table_to_json"):
                self.assertNotIn(word, lua)
            self.assertIn("helpers.write_file('fk5/t.json'", lua)

    def test_the_read_goes_in_batches_and_merges(self):
        cfg = vision.read_config("lab", "lab", vision.Frame((0, 0, 128, 128), 16), ("power",),
                                 False, (), True, link.SKIP_TYPES)
        calls = []

        def fake(_r, lua, tag, what, keep=True):
            calls.append(lua)
            if "local function seen" in lua:
                return {"tick": 5, "roboports": [], "turrets": [], "poles": [[-3.5, 0.5, "small-electric-pole", 2.5, 1]], "networks": {}}
            return {"tick": 5, "cells": {"0,0": {"A": 1}}, "poles": [[1.5, 1.5, "small-electric-pole", 2.5, 1]],
                    "plot_machines": {}, "nghosts": 1}

        with mock.patch.object(link, "read_output", fake):
            got = link.vision_read(object(), cfg, per_call=6)
        self.assertEqual(len(calls), 4)                     # 16 chunks in 3 batches, then wide
        self.assertEqual(got["cells"]["0,0"], {"A": 3})
        self.assertEqual(len(got["poles"]), 4)
        self.assertEqual(got["nghosts"], 3)


class ImageTest(unittest.TestCase):
    def test_png_is_valid(self):
        cv = Canvas(7, 3, (10, 20, 30))
        cv.rect(1, 1, 2, 1, (255, 0, 0))
        data = cv.png()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        w, h = struct.unpack(">II", data[16:24])
        self.assertEqual((w, h), (7, 3))
        idat = data[data.index(b"IDAT") + 4:data.index(b"IEND") - 8]
        raw = zlib.decompress(idat)
        self.assertEqual(len(raw), 3 * (1 + 7 * 3))
        self.assertEqual(raw[1 + 22 + 3:1 + 22 + 6], bytes((255, 0, 0)))

    def test_text_and_image_come_from_one_render(self):
        live = sc(row("assembling-machine-2", "assembling-machine", 5.5, 5.5, w=3, h=3),
                  row("small-electric-pole", "electric-pole", 8.5, 8.5))
        raw = {"poles": [[8.5, 8.5, "small-electric-pole", 2.5, 1]]}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "look.png")
            frame = vision.Frame((0, 0, 32, 32), 2)
            facts = vision.facts_from_read(raw, live)
            text, _ = vision.compose_view(vision.View(2, ("power",)), frame, CAT, live_sc=live,
                                          live=facts)
            img, got = vision.compose_view(vision.View(2, ("power",), path), frame, CAT,
                                           live_sc=live, live=facts)
            self.assertEqual(got, path)
            self.assertTrue(img[-1].startswith("image: "))
            legend = [ln for ln in text if ln.startswith(("cells:", "power"))]
            self.assertEqual([ln for ln in img if ln.startswith(("cells:", "power"))], legend)
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")


class MapLookTest(_OnLabSense):
    def test_a_map_look_reads_counts_not_entities(self):
        cells = {"0,0": {"F": 2, ">": 4}, "1,0": {"A": 1}}

        def fake_read(_r, cfg, tag="vision", per_call=None, timings=None):
            self.assertTrue(cfg["want"]["cells"])
            self.assertEqual(cfg["zoom"], 16)
            if timings is not None:
                timings.append(0.01)
            return {"tick": 7, "cells": cells, "dark": [], "plot_machines": {"iron": 6}}

        snap = mock.Mock(side_effect=AssertionError("a map look takes no snapshot"))
        with mock.patch.object(link, "vision_read", fake_read), \
                mock.patch.object(link, "snapshot", snap):
            lk = look.run(object(), self.dir, CAT, (304, 416, 352, 448), notify="off",
                          view=vision.View(16))
        lines = lk.lines()
        self.assertTrue(lines[0].startswith("look lab --source world, area 304,416,352,448, tick "
                                            "7: map view at zoom 16"))
        rows = panel(lines, "render:")
        self.assertEqual(rows[416], "FA.")
        self.assertIn("plot iron: 6 machine(s), at 310,420 20x24", lines)
        self.assertIn("read in 1 game call(s), 0.01 s (longest 0.01 s)", lines)

    def test_image_path_by_default(self):
        self.assertEqual(look.image_path("g", (1, 2, 3, 4), 8),
                         os.path.join("g", "out", "look-1_2_3_4-z8.png"))


if __name__ == "__main__":
    unittest.main()
