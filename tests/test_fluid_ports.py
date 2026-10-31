"""2.1 (PLAN-2.1 F): fluid ports.

A port may carry a fluid (``port acid_in : in sulfuric-acid @w1``): one pipe connection on the
module's edge, no lanes. The fluid router treats it as a carrier and an attach point, a sealed
module routes its fluids in its own frame, and ``stack A -> B`` threads one pipe through every
cell (two cells' ports meet on one edge, so the stack's own nets lay nothing). Uranium ore takes
sulfuric acid: an electric drill's fluid box is live on it, and a MinerRow on it needs the acid.
"""
import os
import shutil
import tempfile
import unittest

from fkcore import connect, expand, flow, lang
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate
from fkcore.templates import TemplateError, miner_row

CAT = Catalog.load()

#: A chemical cell: its petroleum gas comes in through a fluid port from a pipe outside.
CHEM = """
module PlasCell size 12x10 {
  port gas_in : in petroleum-gas @w4
  plas = ChemPlant<recipe=plastic-bar> @(5, 3)
  cq   = Chest<requester, item=coal, request=20> @(2, 1)
  pbx  = Chest<storage> @(9, 1)
  net g: gas_in -> plas
  net c: cq -> plas
  net p: plas -> pbx
}
gas  = InfinityPipe<fluid=petroleum-gas, rate=30/s> @(0, 4)
cell = PlasCell @(6, 0)
net gas: gas -> cell.gas_in
"""

#: Sulfuric acid from water and sulfur: the water and the sulfur come from outside, and the acid
#: leaves through an out port for a battery plant outside.
ACID = """
module AcidCell size 12x10 {
  port water_in : in water @w2
  port acid_out : out sulfuric-acid @e6
  port sulfur_in : in sulfur @w7
  plant = ChemPlant<recipe=sulfuric-acid> @(5, 3)
  ib    = Chest<requester, item=iron-plate, request=20> @(2, 1)
  net w: water_in -> plant
  net s: sulfur_in -> plant
  net i: ib -> plant
  net a: plant -> acid_out
}
water  = InfinityPipe<fluid=water, rate=30/s> @(0, 2)
sulfur = Chest<requester, item=sulfur, request=50> @(0, 7)
cell   = AcidCell @(6, 0)
bat    = ChemPlant<recipe=battery> @(26, 5)
bq     = Chest<requester, item=iron-plate, request=20> @(30, 2)
cq     = Chest<requester, item=copper-plate, request=20> @(30, 8)
net water: water -> cell.water_in
net sulfur: sulfur -> cell.sulfur_in
net acid: cell.acid_out -> bat
net fe: bq -> bat
net cu: cq -> bat
"""

#: The lab's acid drill cell (2.1): acid in on the west pipe row, through to the east; one
#: electric drill on uranium, its ore onto the cell's through belt.
DRILLS = """
module AcidDrill size 7x7 {
  port acid_in  : in  sulfuric-acid @w0
  port acid_out : out sulfuric-acid @e0
  port ore_in   : in  uranium-ore   @w6
  port ore_out  : out uranium-ore   @e6
  stack acid_in -> acid_out, ore_in -> ore_out
  d = MinerRow<n=1, resource=uranium-ore> @(0, 1)
  net a: acid_in -> d, acid_out
  net o: ore_in, d -> ore_out
}
acid  = InfinityPipe<fluid=sulfuric-acid, rate=10/s> @(0, 0)
cells = Stack<cell=AcidDrill, n=3> @(2, 0)
box   = Chest<storage> @(30, 6)
net acid: acid -> cells.acid_in
net ore: cells.ore_out -> box
"""


def elab(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def build(test, text, size="60x60"):
    """Elaborate, place and route ``text`` as one plot; -> (route.txt, report_checks.txt)."""
    d = tempfile.mkdtemp(prefix="fkfp-")
    test.addCleanup(shutil.rmtree, d, True)
    files = {"t.fk": text,
             "nauvis.surface": f"surface nauvis\nmode play\nterrain none\n"
                               f"place t = t plot 0,0 {size}\n",
             "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\n"
                                 "place --keep pinned\nroute --only stale\nfloorplan\n"
                                 "report_checks\nwrite_layout\n"}
    for name, body in files.items():
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
    code, ctx = flow.run(os.path.join(d, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
    test.assertEqual(code, 0, ctx.log)
    out = []
    for name in ("route.txt", "report_checks.txt"):
        with open(os.path.join(d, "out", name), encoding="utf-8") as fh:
            out.append(fh.read())
    return out


PORT = """
module C size 12x10 {
  port g : PORT
  plas = ChemPlant<recipe=plastic-bar> @(5, 3)
  net g: g -> plas
}
c = C @(6, 0)
"""


class RefusalTest(unittest.TestCase):
    def refused(self, port, words):
        with self.assertRaises(ElabError) as e:
            elab(PORT.replace("PORT", port))
        self.assertIn(words, str(e.exception))

    def test_inout(self):
        self.refused("inout petroleum-gas @w4", "inout is for a belt's port")

    def test_a_lane_pin(self):
        self.refused("in petroleum-gas @w4L", "a pipe has no lanes")

    def test_a_pair(self):
        self.refused("in petroleum-gas | petroleum-gas @w4", "pipes have no lanes")

    def test_two_fluids(self):
        self.refused("in petroleum-gas, water @w4", "a pipe holds one fluid")

    def test_a_fluid_and_an_item(self):
        self.refused("in petroleum-gas, coal @w4", "petroleum-gas, coal need a port each")

    def test_a_fluid_port_elaborates_as_a_pipe(self):
        flat = elab(PORT.replace("PORT", "in petroleum-gas @w4"))
        edges = expand.port_edges(flat, expand.expand_factory(flat, CAT)[0], CAT)
        self.assertEqual([(k, p.fluid) for k, p in edges.items()], [("c/g", "petroleum-gas")])
        self.assertEqual(edges["c/g"].src, edges["c/g"].outside)      # an in port: from outside

    def test_a_stack_carries_one_fluid_end_to_end(self):
        bad = DRILLS.replace("port acid_out : out sulfuric-acid", "port acid_out : out water") \
                    .replace("net a: acid_in -> d, acid_out", "net a: acid_in -> d")
        with self.assertRaises(ElabError) as e:
            elab(bad)
        self.assertIn("a fluid port's two ends carry the same fluid", str(e.exception))
        self.assertIn("sulfuric-acid and water", str(e.exception))


class PortBoxTest(unittest.TestCase):
    def test_an_in_port_takes_inside_and_gives_outside(self):
        pe = expand.PortEdge(inside=(1, 0), outside=(0, 0), src=(0, 0), dst=(1, 0),
                             fluid="water")
        self.assertEqual(connect.port_box(pe, connect.PORT_OUTSIDE).production, "input")
        self.assertEqual(connect.port_box(pe, connect.PORT_INSIDE).production, "output")

    def test_an_out_port_the_other_way(self):
        pe = expand.PortEdge(inside=(1, 0), outside=(0, 0), src=(1, 0), dst=(0, 0),
                             fluid="water")
        self.assertEqual(connect.port_box(pe, connect.PORT_INSIDE).production, "input")
        self.assertEqual(connect.port_box(pe, connect.PORT_OUTSIDE).production, "output")


class UraniumTest(unittest.TestCase):
    def test_a_drill_box_is_live_on_uranium_only(self):
        wet = CAT.fluid_boxes_at("electric-mining-drill", 0.5, 0.5, resource="uranium-ore")
        self.assertTrue(wet)
        self.assertEqual({b.fluid for b in wet}, {"sulfuric-acid"})
        self.assertEqual(CAT.fluid_boxes_at("electric-mining-drill", 0.5, 0.5,
                                            resource="iron-ore"), [])

    def test_a_uranium_row_needs_acid(self):
        specs = miner_row({"n": 2, "resource": "uranium-ore"}, CAT)
        for s in specs:
            self.assertAlmostEqual(s.needs["sulfuric-acid"], 0.25)
            self.assertAlmostEqual(s.makes["uranium-ore"], 0.25)

    def test_a_burner_drill_cannot_mine_uranium(self):
        with self.assertRaises(TemplateError) as e:
            miner_row({"n": 1, "resource": "uranium-ore", "drill": "burner-mining-drill"}, CAT)
        self.assertIn("mine it with electric-mining-drill", str(e.exception))


class RouteTest(unittest.TestCase):
    def test_a_chemical_cell_takes_its_gas_from_outside(self):
        route_txt, checks = build(self, CHEM, "40x20")
        self.assertIn("0 failed", route_txt)
        self.assertIn("4 connected", checks)
        self.assertNotIn("SPILL", checks.replace("0 SPILL", ""))

    def test_an_acid_cell_takes_water_in_and_sends_acid_out(self):
        route_txt, checks = build(self, ACID, "40x20")
        self.assertIn("0 failed", route_txt)
        self.assertNotIn("SPILL", checks.replace("0 SPILL", ""))
        self.assertIn("9 nets: 9 connected", checks)

    def test_a_stack_of_acid_drills_threads_one_pipe(self):
        route_txt, checks = build(self, DRILLS)
        self.assertIn("0 failed", route_txt)
        for k in (1, 2):
            self.assertIn(f"cells/acid_out_{k}", route_txt)
        lines = [ln for ln in route_txt.splitlines() if "cells/acid_out_" in ln]
        self.assertTrue(lines)
        for ln in lines:
            self.assertIn("nothing to lay (its ports meet on one edge)", ln)
        self.assertIn("12 nets: 12 connected", checks)
        self.assertNotIn("SPILL", checks.replace("0 SPILL", ""))


if __name__ == "__main__":
    unittest.main()
