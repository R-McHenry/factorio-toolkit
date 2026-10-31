import unittest

from fkcore import connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

CROSS = """
src = Chest<requester, item=iron-plate, rate=4> @(2, 8)
dst = Chest<provider, limit=8> @(26, 8)
net x: src -> dst
"""
H = 18


def walled(cols=range(11, 17), inserter_at=None):
    """CROSS with a band of other nets' belts, one column each, running south over the whole
    box: too wide for a yellow tunnel, so ``x`` crosses only by promoting them."""
    f = lang.parse(CROSS, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _notes = expand.expand_factory(flat, CAT)
    for c in cols:
        for y in range(H):
            lay.add(fkp.Entity(f"~w{c}/b{y}", "transport-belt", c + 0.5, y + 0.5, 8,
                               {"net": f"w{c}"}))
    if inserter_at is not None:
        x, y = inserter_at
        lay.add(fkp.Entity("~w99/i0", "inserter", x + 0.5, y + 0.5, 4, {"net": "w99"}))
    return flat, lay


def column(r, c):
    return sorted((e for e in r.layout.entities.values() if e.owner == f"~w{c}"),
                  key=lambda e: e.y)


class PromoteTest(unittest.TestCase):
    def test_a_band_too_wide_to_tunnel_is_crossed_by_promotion(self):
        flat, lay = walled()
        r = route.route_layout(flat, lay, CAT, bounds=(0, 0, 30, H))
        self.assertEqual(r.failed, {}, r.lines)
        line = next(l for l in r.lines if l.startswith("routed    x:"))
        self.assertIn("an underground pair now", line)
        self.assertEqual(sum(l.startswith("promoted  w") for l in r.lines), 6, r.lines)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual(rep.nets["x"].status, "connected", rep.lines())
        self.assertEqual(rep.leaks, [])
        for c in range(11, 17):
            col = column(r, c)
            ugs = [e for e in col if e.name == "underground-belt"]
            self.assertEqual([e.attrs["ug"] for e in ugs], ["in", "out"], c)
            self.assertEqual(ugs[1].y - ugs[0].y, 2)
            self.assertEqual(len(col), H - 1)            # 3 belts out, 2 ends in
            self.assertTrue(all(e.dir == 8 for e in col))
            self.assertEqual(len({e.key for e in col}), len(col))
        # each column still carries its items end to end: a belt graph from its first tile
        g = connect.graph(list(r.layout.entities.values()), CAT)
        for c in range(11, 17):
            col = column(r, c)
            seen = g.reach({col[0].key}, f"w{c}")
            self.assertIn(col[-1].key, seen, c)

    def test_a_belt_an_inserter_touches_is_not_promoted(self):
        flat, lay = walled()
        js = route.jobs(flat, lay, CAT)
        ents = list(lay.entities.values())
        free = route._promotable(CAT, ents, js, "x", frozenset(), frozenset())
        self.assertIn((11, 8), free)
        self.assertNotIn((11, 1), free)                  # two belts behind it are needed
        flat, lay = walled(inserter_at=(10, 8))          # picks from 11,8 and drops on 9,8
        ents = list(lay.entities.values())
        free = route._promotable(CAT, ents, js, "x", frozenset(), frozenset())
        for y in (7, 8, 9):
            self.assertNotIn((11, y), free, y)
        self.assertIn((11, 11), free)

    def test_a_net_that_routes_promotes_nothing(self):
        flat, lay = walled(cols=(14,))
        r = route.route_layout(flat, lay, CAT, bounds=(0, 0, 30, H))
        self.assertEqual(r.failed, {}, r.lines)
        self.assertFalse(any(l.startswith("promoted") or "underground pair now" in l for l in r.lines), r.lines)
        self.assertTrue(all(e.name == "transport-belt" for e in column(r, 14)))


if __name__ == "__main__":
    unittest.main()
