"""2.1.33: a unit's passes never lay an order they laid before.

pmbay's green2|redc and cu5 each failed when the other went first. The failed net goes first in
the next pass, so the unit swung between the two orders for every pass it had (8 nets, 10 passes,
the same two answers, twice per pmbay). The same order on the same ground lays the same routes:
an order tried before goes on to the promoting pass.
"""
import unittest
from unittest import mock

from fkcore import route
from tests.test_route import BASE, build, CAT


class CycleTest(unittest.TestCase):
    def test_two_nets_that_block_each_other_take_two_passes(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        real = route._route_one
        rival = {"ore_": "fuel", "fuel": "ore_"}

        def contended(cat, job, ents, *a, **kw):
            other = rival.get(job.net)
            if other and any(e.key.startswith(f"~{other}/") for e in ents):
                return None, f"blocked by {other}"
            return real(cat, job, ents, *a, **kw)

        seen = []

        def progress(attempt, k, order, net, promo=False, which=None):
            if k == 0 and which is None:
                seen.append((attempt, promo, tuple(order)))

        with mock.patch.object(route, "_route_one", contended), \
                mock.patch.object(route, "_progress", progress):
            r = route.route_layout(flat, lay, CAT)
        self.assertEqual(len(r.failed), 1, r.lines)
        plain = [o for _a, promo, o in seen if not promo]
        self.assertEqual(len(plain), len(set(plain)), seen)
        self.assertEqual(len(plain), 2, seen)


if __name__ == "__main__":
    unittest.main()
