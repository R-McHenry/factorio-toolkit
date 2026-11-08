"""2.0.62: the opus run's friction (2026-10-29).

- A net driven by a port that gains a consumer was kept as laid ("kept mall1/fe: its carriers are
  already laid (pinned)"), the new machine never fed and the route said 0 failed.
- A re-route took a hack (move one end a tile); now ``fk build --reroute NET`` and, for any step,
  ``fk build --with 'STEP OPTS'`` for one build without editing the script."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import capture, flow, fkp, link
from fkcore.catalog import Catalog

CAT = Catalog.load()

MALL = """module M size 30x14 {
  port fe_in : in iron-plate @w5
  ga = Assembler<recipe=iron-gear-wheel> @(4, 1)
  gb = Assembler<recipe=iron-gear-wheel> @(10, 1)
  box = Chest<provider, limit=4> @(20, 2)
  net fe: fe_in -> ga
  net g: ga, gb -> box
}
src = Chest<requester, item=iron-plate, request=20> @(1, 6)
m = M @(4, 0)
net feed: src -> m.fe_in
"""

OIL = """module Oil size 26x30 {
  pj1  = Pumpjack                                   @(7, 25)
  pj3  = Pumpjack                                   @(17, 25)
  ref  = Refinery<recipe=basic-oil-processing>      @(10, 13)
  plas = ChemPlant<recipe=plastic-bar>              @(11, 3)
  cq   = Chest<requester, item=coal, request=20>    @(7, 4)
  pbx  = Chest<storage>                             @(18, 4)
  net crude: pj1, pj3 -> ref
  net petro: ref -> plas
  net coal:  cq -> plas
  net plast: plas -> pbx
}
oil = Oil @(2, 2)
"""


class FrictionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fk2062-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("t.fk", MALL)
        self.write("nauvis.surface", "surface nauvis\nterrain none\n"
                                     "place t = t plot 0,0 50x50\n")
        self.write("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\nelaborate\n"
                                       "place --keep pinned\nroute --only stale\nfloorplan\n"
                                       "report_checks\nwrite_layout\n")

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def build(self, extra=None):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None, extra=extra)
        self.assertEqual(code, 0, ctx.log)
        return self.read("out/route.txt"), self.read("out/report_checks.txt")

    def test_a_port_net_that_gains_a_consumer_is_routed_to_it(self):
        self.build()
        self.write("t.fk", MALL.replace("net fe: fe_in -> ga", "net fe: fe_in -> ga, gb"))
        route_txt, checks = self.build()
        self.assertNotIn("kept      m/fe", route_txt)
        # 2.0.74: patched inside the sealed module's own frame (it was laid again whole: with
        # every frame blocked, no branch could be laid inside one)
        self.assertRegex(route_txt, r"patched   m/fe: 1 -> 2, m/gb\.in1: .*; (\d+) of \1 "
                                    r"carriers kept")
        self.assertNotIn("partly-connected", checks)
        self.assertIn("3 nets: 3 connected", checks)

    def test_reroute_lays_a_kept_net_again(self):
        self.build()
        route_txt, _ = self.build()
        self.assertIn("kept      m/fe:", route_txt)
        route_txt, _ = self.build(["route --again m/fe"])
        self.assertIn("stale     m/fe: routed again: asked (--again / fk build --reroute)",
                      route_txt)
        self.assertIn("routed    m/fe:", route_txt)
        self.assertIn("kept      feed:", route_txt)
        # an instance's path: every net inside it; a name that matches nothing is said
        route_txt, _ = self.build(["route --again m,nope"])
        self.assertIn("routed    m/fe:", route_txt)
        self.assertIn("routed    m/g:", route_txt)
        self.assertIn("kept      feed:", route_txt)
        self.assertIn("--again names no net here: nope", route_txt)
        # the script itself is untouched: the next build keeps everything again
        route_txt, _ = self.build()
        self.assertIn("0 routed, 3 kept", route_txt)

    def test_pipes_route_inside_a_sealed_module(self):
        # the opus run's Oil: "every connection tile of its box is taken", whatever the rotation
        self.write("t.fk", OIL)
        route_txt, checks = self.build()
        self.assertRegex(route_txt, r"routed    oil/crude: 2 -> 1, \d+ pipes")
        self.assertRegex(route_txt, r"routed    oil/petro: 1 -> 1, \d+ pipes")
        self.assertIn("4 nets: 4 connected", checks)
        self.assertNotIn("crosses-frame", checks)
        self.assertNotIn("FRAME", checks)

    def test_a_design_captured_goes_anywhere(self):
        # built once (here at world level, in a sealed module), captured, and dropped as a
        # Literal into another module: the same entities, pipes and all
        self.write("t.fk", OIL)
        self.build()
        lay = fkp.load(os.path.join(self.dir, "t.fkp"))
        rows = capture.from_design(lay, CAT, "oil")
        names = [r["name"] for r in rows]
        self.assertEqual(names.count("pumpjack"), 2)
        self.assertIn("pipe", names)
        self.assertIn("pipe-to-ground", names)
        self.assertEqual(min(r["x"] for r in rows) >= 0, True)
        ref = next(r for r in rows if r["name"] == "oil-refinery")
        self.assertEqual(ref["recipe"], "basic-oil-processing")
        capture.write(os.path.join(self.dir, "captured", "oil.json"), {"entities": rows})
        self.write("t.fk", 'module Box size 40x40 {\n'
                           '  o = Literal<file="captured/oil.json"> @(3, 3)\n}\n'
                           "b = Box @(0, 0)\n")
        os.remove(os.path.join(self.dir, "t.fkp"))
        _route, checks = self.build()
        again = fkp.load(os.path.join(self.dir, "t.fkp"))
        got = sorted(e.name for e in again.entities.values() if e.owner.startswith("b/o"))
        self.assertEqual(got, sorted(names))
        self.assertNotIn("FRAME", checks)

    def test_capture_lua_is_safe_and_leaves_the_lab_out(self):
        text = capture.lua_capture("lab", "lab", (0, 0, 10, 10), "t")
        link.assert_safe("/sc " + text)
        self.assertIn("['electric-energy-interface'] = true", text)
        self.assertIn("export_stack", text)

    def test_capture_world_reads_the_surface_it_is_told(self):
        # 2.1.31: a design on the lab surface (Rory's demo) could not be captured: `world` read
        # the run's own surface only
        from unittest import mock
        from fkcore import __main__ as cli
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        seen = []

        def got(_r, surface, force, area, tag="capture"):
            seen.append((surface, force, area))
            return {"bp": "", "n": 1, "names": {"belt": 1}}
        for extra, want in (([], ("nauvis", "player")), (["--surface", "lab"], ("lab", "lab")),
                            (["--surface", "lab", "--force", "player"], ("lab", "player"))):
            with mock.patch.object(cli, "_game_link", return_value=mock.MagicMock()), \
                    mock.patch.object(cli, "_force_surface", return_value=("player", "nauvis")), \
                    mock.patch.object(capture, "from_game", side_effect=got), \
                    mock.patch.object(capture, "names_of_bp", return_value={}):
                rc = cli.main(["capture", tmp, "world", "0,0,4,4", "--to", "c.json"] + extra)
            self.assertIn(rc, (0, None))
            self.assertEqual(seen[-1][:2], want)

    def test_with_adds_options_for_one_build(self):
        lines = flow.parse("route --only stale\ncover robots\n")
        got = flow.with_options(lines, ["cover robots --fresh", "route --effort high"])
        self.assertEqual(got[0].args, ["--only", "stale", "--effort", "high"])
        self.assertEqual(got[1].cmd, "cover_robots")
        self.assertEqual(got[1].args, ["--fresh"])
        self.assertEqual(lines[1].args, [])
        with self.assertRaises(flow.FlowError):
            flow.with_options(lines, ["nonsense --x"])
        with self.assertRaises(flow.FlowError):
            flow.with_options(lines, ["tier --allow red"])          # not in this script


if __name__ == "__main__":
    unittest.main()
