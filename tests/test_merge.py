"""CORE-V1 step 7, on paper: merge two factories linked by robots, chests-to-net, net-to-chests."""
import os
import shutil
import tempfile
import unittest

from fkcore import connect, flow, merge
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()
HERE = os.path.dirname(__file__)
GAME = os.path.join(HERE, "..", "games", "merge")
SCRIPT = os.path.join(HERE, "..", "games", "redgreen", "nauvis.build.fkb")


def state(ctx):
    """{key-free entity identity: key} of the composed surface: what the world would hold."""
    return {(e.name, float(e.x), float(e.y), e.dir): k for k, e in ctx.composed.entities.items()}


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkmerge-")
        for name in ("iron.fk", "gears.fk", "nauvis.surface"):
            shutil.copy(os.path.join(GAME, name), self.dir)
        shutil.copy(SCRIPT, os.path.join(self.dir, "nauvis.build.fkb"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        return ctx

    def report(self, name):
        with open(os.path.join(self.dir, "out", name), encoding="utf-8") as fh:
            return fh.read()

    def connected(self, ctx, factory):
        flat = elaborate_file(os.path.join(self.dir, f"{factory}.fk"), CAT)
        rep = connect.connect(ctx.layouts[factory], CAT, connect.endpoints(flat))
        return {n: r.status for n, r in rep.nets.items()}, rep.leaks

    def test_merge_then_chests_to_net_then_back(self):
        before = self.build()
        s0 = state(before)
        for f, nets in (("iron", {"ore_", "fuel", "plates"}), ("gears", {"plates_in", "gear"})):
            status, leaks = self.connected(before, f)
            self.assertEqual(status, dict.fromkeys(nets, "connected"), f)
            self.assertEqual(leaks, [])

        # 1. merge: one factory, nothing moves, nothing is re-routed
        ch = merge.merge(self.dir, ["iron", "gears"], "works")
        self.assertTrue(any("moved into works.fkp" in l for l in ch.lines))
        merged = self.build()
        self.assertEqual(set(merged.layouts), {"works"})
        s1 = state(merged)
        self.assertEqual(set(s0) - set(s1), set())             # nothing moved or went away
        joins = [s1[i] for i in set(s1) - set(s0)]              # cover joins the two old grids
        self.assertTrue(all(k.startswith("nauvis:works/power/p") for k in joins), joins)
        self.assertLessEqual(len(joins), 3)
        self.assertIn("0 routed, 5 kept (5 pinned from the committed .fkp)", self.report("route.txt"))
        self.assertIn("7 unchanged", self.report("place.txt"))           # 4 iron rows, 3 gears
        self.assertIn("8 pinned cover entities kept", self.report("place.txt"))  # their poles

        # 2. chests-to-net: the robot link becomes a net; only it is routed
        ch = merge.chests_to_net(self.dir, "works", "iron.out", "gears.inbox", "link")
        linked = self.build()
        s1, s2 = state(merged), state(linked)
        gone = {s1[i] for i in set(s1) - set(s2)}
        added = {s2[i] for i in set(s2) - set(s1)}
        chests = {"nauvis:works/iron/out/c0", "nauvis:works/gears/inbox/c0"}
        self.assertTrue(chests <= gone)
        for k in gone - chests:                       # the chests' own routes, and nothing else
            self.assertRegex(k, r"^nauvis:works/~(iron/plates|gears/plates_in)/")
        for k in added:
            self.assertRegex(k, r"^nauvis:works/~link/")
        self.assertTrue(added)
        route_txt = self.report("route.txt")
        self.assertIn("routed    link: 1 -> 1", route_txt)
        self.assertIn("1 routed, 3 kept", route_txt)
        status, leaks = self.connected(linked, "works")
        self.assertEqual(status, {"gears/gear": "connected", "iron/fuel": "connected",
                                  "iron/ore_": "connected", "link": "connected"})
        self.assertEqual(leaks, [])
        self.counts = (len(gone), len(added))

        # 3. net-to-chests takes it back: the chests stand where they stood, both nets connect
        merge.net_to_chests(self.dir, "works", "link",
                            provider={"name": "out", "at": (2, 20), "net": "plates"},
                            requester={"name": "inbox", "at": (2, 2), "net": "plates_in",
                                       "item": "iron-plate", "rate": "1.25/s"})
        back = self.build()
        s3 = state(back)
        for k in chests:
            e = merged.composed.entities[k]
            self.assertIn((e.name, float(e.x), float(e.y), e.dir), s3)
        status, leaks = self.connected(back, "works")
        self.assertEqual(set(status.values()), {"connected"})
        self.assertEqual(set(status), {"gears/gear", "iron/fuel", "iron/ore_", "iron/plates",
                                       "gears/plates_in"})
        self.assertEqual(leaks, [])
        rows = {i for i, k in s1.items() if "/~" not in k}
        self.assertEqual(rows, {i for i, k in s3.items() if "/~" not in k})   # rows, chests, poles
        print(f"\nmerge: {len(s0)} entities kept in place; chests-to-net removed {self.counts[0]} "
              f"(2 chests + their routes), added {self.counts[1]} link carriers; net-to-chests "
              f"restored every non-route entity; routes now {len(set(s3) - set(s1))} new / "
              f"{len(set(s1) - set(s3))} gone vs the merged layout")

    def test_insert_a_component(self):
        self.build()
        merge.merge(self.dir, ["iron", "gears"], "works")
        comp = tempfile.mkdtemp(prefix="fkcomp-")
        try:
            with open(os.path.join(comp, "pipes.fk"), "w") as fh:
                fh.write("src = Chest<requester, item=iron-plate, rate=0.5/s> @(0, 0)\n"
                         "pipes = AsmRow<n=1, recipe=pipe> @(4, 0)\n"
                         "sink = Chest<provider> @(0, 6)\n"
                         "net p_in: src -> pipes\nnet p_out: pipes -> sink\n")
            ch = merge.insert(self.dir, comp, "pipes", "works", (24, 16))
        finally:
            shutil.rmtree(comp, ignore_errors=True)
        self.assertIn("inserted as module PipesFactory at 24,16", str(ch))
        ctx = self.build()
        status, leaks = self.connected(ctx, "works")
        self.assertEqual(status["pipes/p_in"], "connected")
        self.assertEqual(status["pipes/p_out"], "connected")
        self.assertEqual(leaks, [])

    def test_split_to_chest_keeps_the_belt_and_adds_a_branch(self):
        before = self.build()
        gears_lay = before.layouts["gears"]
        merge.split_to_chest(self.dir, "gears", "gear", "spare", (12, 12))     # a provider
        after = self.build()
        route_txt = self.report("route.txt")
        self.assertIn("routed    gear: 1 -> 2", route_txt)         # the box and the spare chest
        self.assertIn("kept      plates_in", route_txt)            # the other net stays pinned
        status, leaks = self.connected(after, "gears")
        self.assertEqual(status, {"gear": "connected", "plates_in": "connected"})
        self.assertEqual(leaks, [])
        keep = {k for k in gears_lay.entities if not k.startswith("~gear/")}
        self.assertTrue(keep <= set(after.layouts["gears"].entities))   # nothing else moved
        self.assertIn("spare/c0", after.layouts["gears"].entities)
        rates = self.report("report_rates.txt")
        self.assertRegex(rates, r"gear\s+iron-gear-wheel")
        # a requester as one more driver: two machines feed the gear row's plates
        merge.split_to_chest(self.dir, "gears", "plates_in", "extra", (2, 6), role="requester",
                             item="iron-plate", rate="0.5/s")
        more = self.build()
        self.assertIn("routed    plates_in: 2 -> 1", self.report("route.txt"))
        status, leaks = self.connected(more, "gears")
        self.assertEqual(set(status.values()), {"connected"})
        self.assertEqual(leaks, [])

    def test_refusals(self):
        self.build()
        with self.assertRaises(merge.MergeError):
            merge.merge(self.dir, ["iron", "nope"], "works")
        merge.merge(self.dir, ["iron", "gears"], "works")
        with self.assertRaises(merge.MergeError):
            merge.chests_to_net(self.dir, "works", "iron.smelt", "gears.inbox")


if __name__ == "__main__":
    unittest.main()
