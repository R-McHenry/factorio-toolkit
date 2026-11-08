"""3.0, several inserters on one machine (Rory, 2026-11-01: "a net needs two or 3 inserters on the
same machine, a common case in seablock earlygame"): where the best hand the force can build
carries less than a machine takes or puts on a belt net, the router lays k of them (at most
route.TAPS_MAX). Nothing read (a lab, a paper game): one each, as before."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import flow, route
from fkcore.catalog import Catalog

CAT = Catalog.load()

CABLE = """module Cab size 20x14 {
  q  = Chest<requester, item=copper-plate, rate=2> @(1, 6)
  a1 = Assembler<recipe=copper-cable> @(7, 2)
  a2 = Assembler<recipe=copper-cable> @(7, 9)
  b  = Chest<provider> @(18, 6)
  net cu: q -> a1, a2
  net k: a1, a2 -> b
}
h = Cab @(2, 2)
"""


def _row(name, stock, enabled):
    return {"entity": name, "item": name, "stock": stock, "known": True, "enabled": enabled}


class TapsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fktaps-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.makedirs(os.path.join(self.dir, "out"))
        for name, text in (("t.fk", CABLE),
                           ("nauvis.surface", "surface nauvis\nterrain none\n"
                                              "place t = t plot 0,0 30x30\n"),
                           ("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\n"
                                                "elaborate\nplace --keep pinned\n"
                                                "route --only stale --hand any\nwrite_layout\n")):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

    def route(self, fast):
        if fast is not None:
            with open(os.path.join(self.dir, "out", "avail.json"), "w", encoding="utf-8") as fh:
                json.dump({"tick": 1, "force": "player", "surface": "nauvis", "networks": 1,
                           "entities": [_row("inserter", 50, True),
                                        _row("fast-inserter", 50 if fast else 0, fast)],
                           "recipes": [], "research": {}}, fh)
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        lay = ctx.layouts["t"]
        out = {}
        for e in lay.entities.values():
            if "inserter" in e.name and e.owner.startswith("~"):
                out[e.owner[1:]] = out.get(e.owner[1:], 0) + 1
        return out

    def test_plain_inserters_double_up_on_two_cable_a_second(self):
        # an assembler makes 2-3 cable/s; a plain inserter puts 1.2/s on a belt: 2-3 out of each
        n = self.route(fast=False)
        k = route._TAPS[("h/k", "h/a1/m0")]
        self.assertIn(k, (2, 3))
        self.assertGreaterEqual(n["h/k"], 2 * k + 1)   # k out of each assembler, 1+ into the chest

    def test_one_chest_loads_its_belt_from_two_sides(self):
        # Rory, 11-01: "one chest can definately fill one belt from multiple sides": the belt
        # wraps the 1x1 requester and takes a plain inserter on each side it passes
        n = self.route(fast=False)
        self.assertGreaterEqual(route._TAPS[("h/cu", "h/q/c0")], 2)
        self.assertGreaterEqual(n["h/cu"], 4)     # 2+ loaders, 1 into each assembler

    def test_one_fast_inserter_is_enough(self):
        self.route(fast=True)
        self.assertNotIn(("h/k", "h/a1/m0"), route._TAPS)

    def test_nothing_read_lays_one_each(self):
        n = self.route(fast=None)
        self.assertEqual(route._TAPS, {})
        self.assertEqual(n["h/k"], 3)

    def test_two_machines_side_by_side_take_two_hands(self):
        # Rory, 11-02: "two machines next to eachother that need more than 1 inserter? Like a ore
        # crusher next to a liquefier": a direct link is sized like a tap, 2 cable/s over 1.2/s
        with open(os.path.join(self.dir, "t.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(PAIR)
        n = self.route(fast=False)
        self.assertGreaterEqual(n["h/k"], 2)
        self.assertEqual(route._link_k("h/k", "h/a/m0", "h/c/m0"), n["h/k"])

    def test_two_machines_side_by_side_one_fast_hand(self):
        with open(os.path.join(self.dir, "t.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(PAIR)
        self.assertEqual(self.route(fast=True)["h/k"], 1)


PAIR = """module Pair size 16x10 {
  q  = Chest<requester, item=copper-plate, rate=2> @(1, 3)
  fe = Chest<requester, item=iron-plate, rate=2> @(14, 3)
  a  = Assembler<recipe=copper-cable> @(4, 2)
  c  = Assembler<recipe=electronic-circuit> @(8, 2)
  net cu: q -> a
  net fe: fe -> c
  b  = Chest<provider> @(9, 8)
  net k: a -> c
  net ec: c -> b
}
h = Pair @(2, 2)
"""


if __name__ == "__main__":
    unittest.main()
