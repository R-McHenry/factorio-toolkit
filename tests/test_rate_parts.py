"""2.1.33: the rate model settles each part of its graph on its own.

The 9-bay megabase loop's graph is nine parts no net joins (one per bay). One bay (rfbay) swung at
damping 0.5, and the one shared damping and pass count held all nine to 1640 passes at 0.25:
18.5 s a solve, several solves a build. Each part now has its own damping and restarts: 4.6 s,
and the other bays settle in their own 40-70 passes.
"""
import unittest

from fkcore import lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

SHORT = """
    src{0}  = Chest<requester, item=iron-plate, rate={1}/s>
    a{0}    = AsmRow<n=1, recipe=pipe>
    b{0}    = AsmRow<n=2, recipe=pipe>
    net iron{0}: src{0} -> a{0}, b{0}
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def parts_of(flat):
    pools = rates._pools(flat)
    ends, _feeds, _outs = rates._structure(flat, pools)
    machines = rates._buffer_view(flat)
    mine = {}
    return rates._parts(ends, machines, mine)


def util(model, path):
    us = {round(model.util[k], 12) for k in model.flat.insts[path].machines}
    assert len(us) == 1, us
    return us.pop()


class RatePartsTest(unittest.TestCase):
    def test_parts_no_net_joins_solve_as_they_would_alone(self):
        both = SHORT.format(1, 1.5) + SHORT.format(2, 0.6) + """
            sink = Chest<provider>
            sink2 = Chest<provider>
            net pipes: a1, b1 -> sink
            net pipes2: a2, b2 -> sink2
        """
        flat = flat_of(both)
        names = sorted(sorted(n for (n, _i), _e in p[0]) for p in parts_of(flat))
        self.assertEqual(names, [["iron1", "pipes"], ["iron2", "pipes2"]])
        m = rates.solve(flat)
        alone1 = rates.solve(flat_of(SHORT.format(1, 1.5) + """
            sink = Chest<provider>
            net pipes: a1, b1 -> sink"""))
        alone2 = rates.solve(flat_of(SHORT.format(2, 0.6) + """
            sink = Chest<provider>
            net pipes2: a2, b2 -> sink"""))
        self.assertAlmostEqual(util(m, "a1"), util(alone1, "a1"))
        self.assertAlmostEqual(util(m, "a1"), 0.5)
        self.assertAlmostEqual(util(m, "b2"), util(alone2, "b2"))
        self.assertAlmostEqual(util(m, "b2"), 0.2)
        self.assertEqual(m.passes, max(alone1.passes, alone2.passes))
        self.assertLess(m.residual, 1e-9)

    def test_a_machine_on_two_nets_joins_them(self):
        flat = flat_of(SHORT.format(1, 1.5) + SHORT.format(2, 0.6) + """
            sink = Chest<provider>
            net pipes: a1, b1, a2, b2 -> sink
        """)
        names = [sorted(n for (n, _i), _e in p[0]) for p in parts_of(flat)]
        self.assertEqual(names, [["iron1", "iron2", "pipes"]])


if __name__ == "__main__":
    unittest.main()
