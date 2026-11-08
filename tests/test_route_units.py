"""3.0.1: route-once across compile units.

The review of 3.0.0 found that a world net's group try could lift any sealed module's routes
(the top level counted every unit as nested), and that FK_NEGOTIATE=1 ran 2.1's own passes, which
skipped seeds, holds and the failure memo. A group try now lifts a nested unit's nets only when
the failing net's way enters that unit's frame, and a negotiated route is laid through the same
route-once loop as any.
"""
import os
import unittest
from unittest import mock

from fkcore import expand, fkp as fkpmod, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

# a thin sealed module whose belt runs down its east edge, and a world net beside it
BESIDE = """
module Edge size 1x10 {
  c = Chest<requester, item=iron-plate, rate=1> @(0, 0)
  b = Chest<provider> @(0, 9)
  net e: c -> b
}
m = Edge @(0, 0)
s = Chest<requester, item=copper-plate, rate=1> @(1, 0)
t = Chest<provider> @(1, 9)
net top: s -> t
"""


def placed(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    return flat, expand.expand_factory(flat, CAT)[0]


class UnitsTest(unittest.TestCase):
    def test_a_world_net_never_lifts_a_module_it_only_runs_beside(self):
        flat, lay = placed(BESIDE)
        # the world net's way runs within GROUP_MARGIN of the module's belt (what 3.0.0 lifted)
        r0 = route.route_layout(flat, lay, CAT)
        tiles = {}
        for e in r0.layout.entities.values():
            if e.key.startswith("~"):
                tiles.setdefault(e.key[1:].rsplit("/", 1)[0], set()).update(
                    fkpmod.tiles_of(CAT, e))
        g = route.GROUP_MARGIN
        near = {(x + dx, y + dy) for x, y in tiles["top"] for dx in range(-g, g + 1)
                for dy in range(-g, g + 1)}
        self.assertTrue(tiles["m/e"] & near, tiles)
        real = route._route_one
        calls = {"top": 0}

        def first_fails(cat, job, ents, *a, **kw):
            if job.net == "top":
                calls["top"] += 1
                if calls["top"] == 1:
                    return None, "made to fail"
            return real(cat, job, ents, *a, **kw)

        seen = []

        def progress(attempt, k, order, net, promo=False, which=None):
            seen.append((which, tuple(order), net))

        with mock.patch.object(route, "_route_one", first_fails), \
                mock.patch.object(route, "_progress", progress):
            r = route.route_layout(flat, lay, CAT, group_budget=30)
        laid = {e.key for e in r.layout.entities.values() if e.key.startswith("~m/")}
        self.assertTrue(laid, r.lines)               # the module's net stands as it was laid
        groups = [o for which, o, _n in seen if which and which.startswith("the group of top")]
        self.assertFalse(any(n.startswith("m/") for o in groups for n in o), groups)

    def test_negotiated_routes_go_through_route_once(self):
        flat, lay = placed(BESIDE)
        seen = []

        def progress(attempt, k, order, net, promo=False, which=None):
            seen.append(which)

        with mock.patch.dict(os.environ, {"FK_NEGOTIATE": "1"}), \
                mock.patch.object(route, "_progress", progress):
            r = route.route_layout(flat, lay, CAT)
        self.assertFalse(r.failed, r.lines)
        self.assertIn("negotiate", seen)
        self.assertIn("pass 1", seen)                # laid through lay_net, not 2.1's passes

    def test_negotiation_leaves_a_seeded_net_to_its_seed(self):
        flat, lay = placed(BESIDE)
        negotiated = []
        real = route._negotiate

        def spy(flat_, cat, js, order, *a, **kw):
            negotiated.extend(order)
            return real(flat_, cat, js, order, *a, **kw)

        seed = [fkpmod.Entity("~top/seed0", "transport-belt", 1.5, 4.5, 8, {})]
        with mock.patch.dict(os.environ, {"FK_NEGOTIATE": "1"}), \
                mock.patch.object(route, "_negotiate", spy):
            route.route_layout(flat, lay, CAT, seeds={"top": seed})
        self.assertNotIn("top", negotiated)


if __name__ == "__main__":
    unittest.main()
