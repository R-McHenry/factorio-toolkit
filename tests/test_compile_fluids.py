"""3.1.4: fluid nets are compile units too. A sealed unit's pipe nets are laid with the unit, in
its frame (they went to one whole-world pass after the belts, keyed and stored by no unit, so a
module of pipes never compiled: PLAN-3.0 §4's "not done", the megabelt's refinery and cracking
columns), a twin takes them, the store holds the unit whole, and a unit whose routes stand is
keyed as a fresh one and written to the store when the store has lost it."""
import json
import os
import tempfile
import unittest

from fkcore import compiled, connect, expand, fkp as fkpmod, fluid_route, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

# the megabelt's PlasticN (lab-session/megabelt fencells.fk): the gas pipe runs straight down
# the cell's west column through the plant, the coal belt and the plastic belt beside it, so
# stacked cells touch only at their port tiles. (A cell whose pipe runs along its edge, as in
# agent/docs/examples/plastic-cell.fk, is routed on its own each time: a twin's pipes moved up
# a cell would join the cell below along the edge, and the judge refuses them.)
CELL = """
kind Plastics = Machine<entity=chemical-plant, recipe=plastic-bar>
module PlasticN size 10x3 {
  port gas_in  : in  petroleum-gas @n0
  port gas_out : out petroleum-gas @s0
  port p_in    : in  plastic-bar   @n5
  port p_out   : out plastic-bar   @s5
  port c_in    : in  coal          @n6
  port c_out   : out coal          @s6
  stack gas_out -> gas_in, p_out -> p_in, c_out -> c_in
  plant = Plastics @(1, 0, rot 3)
  pole = Pole @(4, 1)
  net g: gas_in -> plant, gas_out
  net c: c_in -> plant, c_out
  net p: p_in, plant -> p_out
}
"""

# gas and coal come in at the north end of the column, plastic leaves at the south end
STACK = CELL + """
gas   = InfinityPipe<fluid=petroleum-gas, rate=80/s> @(2, 0)
coal  = Chest<requester, item=coal, rate=4/s> @(8, 0)
line  = Stack<cell=PlasticN, n=4> @(2, 4)
box   = Chest<provider, limit=8> @(7, 20)
net fuel:    coal -> line.c_in
net gas_:    gas -> line.gas_in
net plastic: line.p_out -> box
"""

# a module of pipes alone: water in, through a boiler's water box, out the other side
PIPES = """
module WaterCell size 10x6 {
  port w_in  : in  water @w2
  port w_out : out water @e2
  b = Boiler @(3, 1)
  net w: w_in -> b, w_out
}
pump = OffshorePump<rate=1200/s> @(0, 12)
wa = WaterCell @(4, 0)
wb = WaterCell @(16, 0)
sink = Boiler @(30, 1)
net w0: pump -> wa.w_in
net w1: wa.w_out -> wb.w_in
net w2: wb.w_out -> sink
"""


def placed(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    return flat, expand.expand_factory(flat, CAT)[0]


def carriers(lay, prefix, dx=0, dy=0):
    return sorted((e.key.replace(prefix, "@", 1), e.name, e.x - dx, e.y - dy, e.dir)
                  for k, e in lay.entities.items() if k.startswith("~" + prefix))


def pipes(lay, net):
    return sorted((e.name, e.x, e.y, e.dir) for e in lay.entities.values()
                  if e.owner == "~" + net and CAT.kind(e.name) in ("pipe", "pipe-to-ground"))


def line_of(r, head):
    return next(ln for ln in r.lines if ln.startswith(head))


def connected(flat, lay):
    """The fluid nets' status and the SPILL checks naming one (the ports as the nets' ends)."""
    edges = fluid_route.port_edges(flat, lay, CAT)
    rep = connect.connect(lay, CAT, connect.endpoints(flat), edges)
    fluids = route.fluid_nets(flat, CAT)
    return ({n: x.status for n, x in rep.nets.items() if n in fluids},
            [c for c in rep.checks if c.code == "SPILL" and any(f in c.where for f in fluids)])


class FluidUnitsTest(unittest.TestCase):
    def test_a_cells_pipe_is_laid_with_the_cell_and_a_twin_takes_it(self):
        flat, lay = placed(STACK)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertIn("4 sealed modules", line_of(r, "compile"))
        self.assertIn("3 laid as a twin", line_of(r, "compile"))
        self.assertTrue(pipes(r.layout, "line/0/g"))
        # the twins' pipes are the first cell's, moved up a cell each
        for k in (1, 2, 3):
            self.assertEqual(carriers(r.layout, "line/0/"), carriers(r.layout, f"line/{k}/", 0, -3 * k))
            self.assertIn("compiled once", line_of(r, f"routed    line/{k}/g"))
        self.assertEqual(sorted(r.compiled["line/0"]["nets"]), ["line/0/c", "line/0/g", "line/0/p"])
        self.assertEqual(r.compiled["line/0"]["from"], "routed")
        self.assertEqual(r.compiled["line/1"]["from"], "twin line/0")
        statuses, checks = connected(flat, r.layout)
        self.assertEqual(set(statuses.values()), {"connected"})
        self.assertEqual(checks, [])
        self.assertEqual(fkpmod.invariants(r.layout, CAT, nets=flat.nets), [])
        self.assertEqual(route.seal_checks(flat, r.layout, CAT), [])

    def test_the_store_holds_the_cell_whole_and_lays_its_pipe_from_there(self):
        with tempfile.TemporaryDirectory() as store:
            flat, lay = placed(STACK)
            first = route.route_layout(flat, lay, CAT, store=store)
            self.assertEqual(first.failed, {})
            self.assertEqual(first.compiled["line/0"]["stored"], 1)
            key = first.compiled["line/0"]["key"]
            with open(os.path.join(store, "PlasticN", f"{key}.json"), encoding="utf-8") as fh:
                entry = json.load(fh)
            self.assertEqual(sorted(entry["nets"]), ["c", "g", "p"])
            self.assertTrue(any(e[1] == "pipe" for e in entry["nets"]["g"]))
            # the next build, the line elsewhere: every cell from the store, pipes included
            moved = STACK.replace("@(2, 0)", "@(20, 30)").replace("@(8, 0)", "@(26, 30)") \
                .replace("@(2, 4)", "@(20, 34)").replace("@(7, 20)", "@(25, 50)")
            flat2, lay2 = placed(moved)
            again = route.route_layout(flat2, lay2, CAT, store=store)
            self.assertEqual(again.failed, {})
            self.assertEqual({u: c["from"] for u, c in again.compiled.items()},
                             {f"line/{k}": "store" for k in range(4)})
            self.assertEqual(carriers(first.layout, "line/0/"),
                             carriers(again.layout, "line/0/", 18, 30))
            self.assertIn("4 from the compiled store", line_of(again, "compile"))
            statuses, checks = connected(flat2, again.layout)
            self.assertEqual(set(statuses.values()), {"connected"})
            self.assertEqual(checks, [])

    def test_a_module_of_pipes_alone_compiles(self):
        flat, lay = placed(PIPES)
        with tempfile.TemporaryDirectory() as store:
            r = route.route_layout(flat, lay, CAT, store=store)
            self.assertEqual(r.failed, {})
            self.assertEqual(r.compiled["wa"]["from"], "routed")
            self.assertEqual(r.compiled["wb"]["from"], "twin wa")
            self.assertEqual(r.compiled["wa"]["stored"], 1)
            self.assertEqual(pipes(r.layout, "wa/w"),
                             [(n, x - 12, y, d) for n, x, y, d in pipes(r.layout, "wb/w")])
            self.assertTrue(pipes(r.layout, "wa/w"))
            statuses, checks = connected(flat, r.layout)
            self.assertEqual(set(statuses.values()), {"connected"})
            self.assertEqual(checks, [])

    def test_a_standing_unit_is_keyed_as_a_fresh_one_and_stored_again(self):
        # the megabelt's Circuit copy: its store was emptied, and the modules whose routes stood
        # were never written again (a unit was keyed only when a belt net of it was stale)
        with tempfile.TemporaryDirectory() as store:
            flat, lay = placed(STACK)
            first = route.route_layout(flat, lay, CAT, store=store)
            key = first.compiled["line/0"]["key"]
            for name in os.listdir(os.path.join(store, "PlasticN")):
                os.remove(os.path.join(store, "PlasticN", name))
            patch = {}
            for e in first.layout.entities.values():
                if e.owner.startswith("~"):
                    patch.setdefault(e.owner[1:], []).append(e)
            again = route.route_layout(flat, lay, CAT, store=store, patch=patch)
            self.assertEqual(again.failed, {})
            self.assertEqual(sorted(again.kept), sorted(patch))
            self.assertEqual(again.compiled["line/0"]["from"], "standing")
            self.assertEqual(again.compiled["line/0"]["key"], key)   # the key is what it is laid to
            self.assertEqual(again.compiled["line/0"]["stored"], 1)
            self.assertEqual(again.compiled["line/1"]["stored"], 0)  # the same key, once
            self.assertIn("1 stored", line_of(again, "compile"))

    def test_a_unit_half_standing_takes_the_rest_from_the_store(self):
        with tempfile.TemporaryDirectory() as store:
            flat, lay = placed(STACK)
            first = route.route_layout(flat, lay, CAT, store=store)
            key = first.compiled["line/0"]["key"]
            # the belts of every cell stand; the pipes are to be laid again
            patch = {}
            for e in first.layout.entities.values():
                if e.owner.startswith("~") and not e.owner.endswith("/g"):
                    patch.setdefault(e.owner[1:], []).append(e)
            again = route.route_layout(flat, lay, CAT, store=store, patch=patch)
            self.assertEqual(again.failed, {})
            self.assertEqual(again.compiled["line/0"]["key"], key)
            self.assertEqual(again.compiled["line/0"]["from"], "store")
            self.assertEqual(again.compiled["line/0"]["laid"], ["line/0/g"])
            self.assertEqual(pipes(again.layout, "line/2/g"), pipes(first.layout, "line/2/g"))
            self.assertEqual(again.compiled["line/0"]["stored"], 0)

    def test_the_fluid_pass_after_the_belts_takes_the_rest(self):
        # the nets outside every sealed module still go to the one pass after the belts
        flat, lay = placed(STACK)
        r = route.route_layout(flat, lay, CAT)
        self.assertIn("routed    gas_:", "\n".join(r.lines))
        self.assertTrue(pipes(r.layout, "gas_"))


if __name__ == "__main__":
    unittest.main()
