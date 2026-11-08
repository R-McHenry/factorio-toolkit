"""2.1.33: a unit's passes never lay an order they laid before.

pmbay's green2|redc and cu5 each failed when the other went first. The failed net goes first in
the next pass, so the unit swung between the two orders for every pass it had (8 nets, 10 passes,
the same two answers, twice per pmbay). The same order on the same ground lays the same routes:
an order tried before goes on to the promoting pass.

3.0: there are no passes over the unit any more. Each net is laid once (pass 1); the net that
fails gets its group try, which never lays one order twice, then one promoting search.
"""
import unittest
from unittest import mock

from fkcore import route
from tests.test_route import BASE, build, CAT


class CycleTest(unittest.TestCase):
    def test_two_nets_that_block_each_other_never_repeat_an_order(self):
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
            seen.append((which, k, tuple(order), net))

        with mock.patch.object(route, "_route_one", contended), \
                mock.patch.object(route, "_progress", progress):
            r = route.route_layout(flat, lay, CAT, group_budget=30)
        self.assertEqual(len(r.failed), 1, r.lines)
        # pass 1 lays each net once
        first = [net for which, _k, _o, net in seen if which == "pass 1"]
        self.assertEqual(len(first), len(set(first)), seen)
        self.assertIn("ore_", first)
        self.assertIn("fuel", first)
        # the group try lays no order twice
        tries = [o for which, k, o, _n in seen if which and which.startswith("the group of")
                 and k == 0]
        self.assertEqual(len(tries), len(set(tries)), seen)


if __name__ == "__main__":
    unittest.main()
