"""2.0.73: the friction of the 10-30 live run (C:\\fk-player\\runs\\20261030-1602-opus).

- ``fk decon`` failed in the live game with "'end' expected near <eof>": the one-line join of its
  Lua let a trailing ``-- comment`` comment out the rest of the script.
- ``fk build`` sat 10+ minutes in its second report_rates: a coal belt ring made the routed
  model's required flows go round and round, more every round.
- A paste that re-laid the mains while their belts were SHORT stopped the base, and write_layout
  had overwritten world.fkp with no copy of the layout before it.
"""
import os
import shutil
import tempfile
import time
import unittest

from fkcore import flow, fkp, lanes, link
from fkcore import throughput as tp
from fkcore.catalog import Catalog
from fkcore.sense import Verdict

CAT = Catalog.load()
PLATE = "iron-plate"


class LuaOneLineTest(unittest.TestCase):
    def test_a_trailing_comment_ends_at_its_line(self):
        body = "local a = f(x)   -- note\nrcon.print(a)\n"
        self.assertEqual(link.lua_one_line(body), "local a = f(x) rcon.print(a)")

    def test_dashes_in_a_string_stay(self):
        body = "rcon.print('a -- b')  -- why\nrcon.print(\"c--d\")"
        self.assertEqual(link.lua_one_line(body), "rcon.print('a -- b') rcon.print(\"c--d\")")

    def test_an_escaped_quote_does_not_end_the_string(self):
        body = "rcon.print('it\\'s -- here') -- gone"
        self.assertEqual(link.lua_one_line(body), "rcon.print('it\\'s -- here')")

    def test_fk_decon_sends_its_whole_script(self):
        for cancel in (False, True):
            for names in ((), ("passive-provider-chest",)):
                code = link.lua_one_line(link.lua_decon_area("nauvis", "player", (16, -5, 17, -4),
                                                             names, cancel))
                self.assertTrue(code.endswith("rcon.print(helpers.table_to_json({by = by, "
                                              "robots = robots}))"), code)
                self.assertNotIn("--", code)
                link.assert_safe("/sc " + code)


def ring_layout():
    """A belt ring 5x5 (east on top, south on the right, west at the bottom, north on the left),
    fed by a side-load onto its top and taken from by an inserter on its right."""
    rows = [f"e r/t{x} transport-belt {x}.5,0.5 E net=a" for x in range(0, 4)]
    rows += [f"e r/r{y} transport-belt 4.5,{y}.5 S net=a" for y in range(0, 4)]
    rows += [f"e r/b{x} transport-belt {x}.5,4.5 W net=a" for x in range(4, 0, -1)]
    rows += [f"e r/l{y} transport-belt 0.5,{y}.5 N net=a" for y in range(4, 0, -1)]
    rows += [f"e s/b{j} transport-belt 2.5,{-j - 0.5} S net=a" for j in range(4)]
    rows += ["e r/i0 inserter 5.5,2.5 W net=a", "e c/c0 wooden-chest 6.5,2.5"]
    return fkp.loads("fkp 1 factory t\n" + "\n".join(rows))


class RingTest(unittest.TestCase):
    def test_a_belt_ring_settles(self):
        lg = lanes.build(ring_layout(), CAT)
        t0 = time.monotonic()
        r = tp.solve(lg, supply={("s/b3", "L"): {PLATE: 10}}, demand={("c/c0", ""): {PLATE: 0.5}})
        self.assertLess(time.monotonic() - t0, 10)
        self.assertLess(r.rounds, 400)                  # each item's flows settled
        self.assertAlmostEqual(r.delivered[("c/c0", "")][PLATE], 0.5)
        req = max(sum(t.values()) for t in r.required.values())
        self.assertLess(req, 11)                        # no flow piled up going round

    def test_a_ring_is_entered_where_it_is_fed(self):
        lg = lanes.build(ring_layout(), CAT)
        order = tp._topo(lg)
        pos = {v: i for i, v in enumerate(order)}
        back = [e for e in lg.edges() if pos[e.dst] <= pos[e.src]]
        self.assertLessEqual(len(back), 2)               # one closing edge per lane of the ring

    def test_the_coupling_stops_on_its_budget(self):
        lg = lanes.build(ring_layout(), CAT)
        mach = {("c/c0", ""): tp.Machine({PLATE: 1.0}, {})}
        r = tp.solve(lg, supply={("s/b3", "L"): {PLATE: 10}}, machines=mach, budget=-1)
        self.assertEqual(r.outer, 1)


class LayoutHistoryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ctx = flow.Ctx(self.dir, os.path.join(self.dir, "x.fkb"), CAT,
                            os.path.join(self.dir, "out"))
        self.path = os.path.join(self.dir, "world.fkp")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def history(self):
        folder = os.path.join(self.dir, "out", "fkp-history")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_the_layout_before_is_kept(self):
        flow._keep_prior(self.ctx, self.path, "new")         # nothing there yet
        self.assertEqual(self.history(), [])
        with open(self.path, "w") as fh:
            fh.write("old")
        flow._keep_prior(self.ctx, self.path, "old")         # unchanged: no copy
        self.assertEqual(self.history(), [])
        flow._keep_prior(self.ctx, self.path, "new")
        [name] = self.history()
        self.assertTrue(name.startswith("world.") and name.endswith(".fkp"))
        with open(os.path.join(self.dir, "out", "fkp-history", name)) as fh:
            self.assertEqual(fh.read(), "old")

    def test_only_the_newest_are_kept(self):
        folder = os.path.join(self.dir, "out", "fkp-history")
        os.makedirs(folder)
        for k in range(12):
            with open(os.path.join(folder, f"world.20261030-0000{k:02d}.fkp"), "w") as fh:
                fh.write(str(k))
        with open(os.path.join(folder, "world-b.20261030-000000.fkp"), "w") as fh:
            fh.write("another file's")
        with open(self.path, "w") as fh:
            fh.write("old")
        flow._keep_prior(self.ctx, self.path, "new")
        mine = [f for f in self.history() if f.startswith("world.")]
        self.assertEqual(len(mine), flow.KEEP_PRIOR)
        self.assertIn("world-b.20261030-000000.fkp", self.history())


class CarriersTakenUpTest(unittest.TestCase):
    def test_the_belts_a_paste_takes_up(self):
        class Rep:
            verdicts = [Verdict("unowned", "transport-belt", 2.5, 2.5),
                        Verdict("unowned", "transport-belt", 3.5, 2.5, ghost=True),
                        Verdict("unowned", "inserter", 4.5, 2.5),
                        Verdict("other-entity", "assembling-machine-1", 9.5, 9.5,
                                under=[("underground-belt", 9, 9, None, False, True),
                                       ("pipe", 10, 9, None, True, True)]),
                        Verdict("ok", "transport-belt", 20.5, 20.5)]
        ctx = flow.Ctx(tempfile.gettempdir(), "x.fkb", CAT, tempfile.gettempdir())
        self.assertEqual(flow._carriers_taken_up(ctx), 0)
        ctx.last_diff = Rep
        self.assertEqual(flow._carriers_taken_up(ctx), 2)


if __name__ == "__main__":
    unittest.main()
