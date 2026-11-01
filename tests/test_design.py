"""3.0, the design database on disk (fkcore.design): the route step writes one file per net as
it lands, the next build starts from them, a held net stands as it is, and fk status reads them."""
import os
import re
import shutil
import tempfile
import unittest

from fkcore import design, fkp, flow
from fkcore.catalog import Catalog

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "redgreen")


class DesignFilesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkdesign-")
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_net_file_round_trips(self):
        e = fkp.Entity("~a|b/b0", "transport-belt", 1.5, 2.5, 4, {"net": "a|b"})
        design.write_net(self.out, "main", "a|b", "unrouted", [e], "no way\npast x", 2.25, "k1")
        path = design.net_path(self.out, "main", "a|b")
        self.assertNotIn("|", os.path.basename(path))
        rec = design.read_net(path)
        self.assertEqual((rec["net"], rec["status"], rec["why"], rec["took"], rec["key"]),
                         ("a|b", "unrouted", "no way past x", 2.2, "k1"))
        self.assertEqual([(x.key, x.x, x.y) for x in rec["ents"]], [("~a|b/b0", 1.5, 2.5)])
        design.write_net(self.out, "main", "mall/fe", "routed", [])
        self.assertTrue(os.path.exists(os.path.join(self.out, "design", "main", "nets", "mall",
                                                    "fe.net")))
        self.assertEqual(sorted(design.read_all(self.out, "main")), ["a|b", "mall/fe"])
        self.assertIsNotNone(design.set_status(self.out, "main", "a|b", "held"))
        self.assertEqual(design.read_net(path)["status"], "held")
        design.set_status(self.out, "main", "a|b", "unrouted", design.UNROUTED_BY_YOU)
        self.assertEqual(design.read_net(path)["ents"], [])
        lines = design.status_lines(self.out, "main")
        self.assertEqual(lines[0], "main: 2 nets: 1 routed, 1 unrouted")
        self.assertIn("unrouted a|b 2.2 s: unrouted by you", lines[1])


class DesignFlowTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkdesign-")
        for name in ("main.fk", "nauvis.surface", "nauvis.build.fkb"):
            shutil.copy(os.path.join(GAME, name), self.dir)
        self.script = os.path.join(self.dir, "nauvis.build.fkb")
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self, **kw):
        return flow.run(self.script, cat=CAT, echo=lambda _line: None, **kw)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def test_the_route_step_writes_a_file_per_net_and_starts_from_them(self):
        self.build(to="route")                         # no paste: no committed .fkp
        recs = design.read_all(self.out, "main")
        self.assertEqual(len(recs), 12)
        self.assertEqual({r["status"] for r in recs.values()}, {"routed"})
        self.assertIsNone(design.read_now(self.out, "main"))       # done: nothing in progress
        self.assertTrue(os.path.exists(os.path.join(self.out, "design", "main", "base.fkp")))
        # the next build keeps every one of them (it stopped before the paste)
        self.build(to="route")
        self.assertIn("0 routed, 12 kept", self.read("out/route.txt"))
        self.assertEqual({r["status"] for r in design.read_all(self.out, "main").values()},
                         {"kept"})

    def test_a_held_net_stands_as_it_is(self):
        self.build(to="route")
        gear = design.read_all(self.out, "main")["gear"]
        design.set_status(self.out, "main", "gear", "held")
        self.build(to="route")
        route_txt = self.read("out/route.txt")
        self.assertIn(f"main: held gear: {len(gear['ents'])} carriers stand as you hold them",
                      route_txt)
        rec = design.read_all(self.out, "main")["gear"]
        self.assertEqual((rec["status"], len(rec["ents"])), ("held", len(gear["ents"])))
        self.assertIn("held: gear", "\n".join(design.status_lines(self.out, "main")))

    def test_the_route_step_alone_lays_the_nets_named(self):
        # 3.0 `fk route gear` (python -m fkcore step SCRIPT route gear): the route line alone
        from fkcore.__main__ import main
        self.build(to="route")
        code = main(["step", self.script, "route", "gear"])
        self.assertEqual(code, 0)
        route_txt = self.read("out/route.txt")
        self.assertIn("main: 1 routed, 11 kept", route_txt)
        self.assertIn("stale     gear: routed again: asked", route_txt)
        self.assertEqual(main(["step", self.script, "place", "gear"]), 2)   # nets: route only

    def test_the_routing_library_pieces(self):
        # Rory, 11-01: no route --via in the language; a waypoint, a merge and a split are sealed
        # modules in the kickoff's routing.fk, placed and wired like any instance
        shutil.copy(os.path.join(os.path.dirname(__file__), "..", "kickoff", "template", "game",
                                 "routing.fk"), self.dir)
        fk = 'import Waypoint, Merge, Split from "routing.fk"\n' + self.read("main.fk")
        for old, new in (
                ("labs  = LabRow<n=10>",
                 "wp    = Waypoint<item=iron-gear-wheel>  @(8, 28)\n"
                 "mg    = Merge<a=automation-science-pack, b=logistic-science-pack>  @(4, 40)\n"
                 "sp    = Split<item=copper-plate>  @(4, 16)\n"
                 "labs  = LabRow<n=10>"),
                ("net gear:   gears -> red, belts, ins",
                 "net gear:   gears -> wp.i\nnet gear2:  wp.o -> red, belts, ins"),
                ("net copper: copper_smelt -> cable, red",
                 "net copper: copper_smelt -> sp.i\nnet cu_a: sp.a -> cable\nnet cu_b: sp.b -> red"),
                ("net packs:  red, green -> labs",
                 "net pk_r: red -> mg.a\nnet pk_g: green -> mg.b\nnet packs: mg.o -> labs")):
            self.assertIn(old, fk)
            fk = fk.replace(old, new)
        with open(os.path.join(self.dir, "main.fk"), "w", encoding="utf-8") as fh:
            fh.write(fk)
        self.build(to="report_checks")
        route_txt = self.read("out/route.txt")
        self.assertRegex(route_txt, r"routed    wp/p: 1 -> 1, 3 belts")
        self.assertRegex(route_txt, r"routed    mg/p: 2 -> 1, .*1 merges")
        self.assertRegex(route_txt, r"routed    sp/p: 1 -> 2, .*1 splitters")
        self.assertIn("main: 20 nets: 20 connected", self.read("out/report_checks.txt"))

    def test_a_net_routed_through_its_seed(self):
        # 3.0 `fk seed NET 'splitter X,Y S'`: the player pins a splitter of gear's; the router lays
        # the rest of gear through it, and later builds keep the seed
        from fkcore.__main__ import main
        self.build(to="route")
        self.assertEqual(main(["seed", self.dir, "gear", "splitter 9,30.5 S"]), 0)
        rec = design.read_all(self.out, "main")["gear"]
        self.assertEqual((rec["status"], rec["seed"]), ("seeded", ["~gear/p0"]))
        self.assertEqual(main(["step", self.script, "route"]), 0)
        route_txt = self.read("out/route.txt")
        self.assertIn("stale     gear: routed again: seeded by you (fk seed)", route_txt)
        self.assertRegex(route_txt, r"routed    gear: 1 -> 3, through your seed, 1 carriers; \d+ carriers "
                                    r"into it at 9,29; \d+ carriers out of it at 8,31; \d+ "
                                    r"carriers out of it at 9,31")
        rec = design.read_all(self.out, "main")["gear"]
        self.assertEqual((rec["status"], rec["seed"]), ("routed", ["~gear/p0"]))
        self.assertIn(("splitter", 9, 30.5), {(e.name, e.x, e.y) for e in rec["ents"]})
        self.build(to="report_checks")
        self.assertIn("12 nets: 12 connected", self.read("out/report_checks.txt"))
        self.assertEqual(design.read_all(self.out, "main")["gear"]["seed"], ["~gear/p0"])
        self.assertEqual(main(["seed", self.dir, "gear", "splitter nowhere"]), 2)

    def test_route_area_routes_the_nets_there_and_the_rest_stand(self):
        # route --area: pin everything outside an area, work within it
        from fkcore.__main__ import main
        self.build(to="route")
        before = {n: sorted((e.x, e.y) for e in r["ents"])
                  for n, r in design.read_all(self.out, "main").items()}
        self.assertEqual(main(["step", self.script, "route", "--with",
                               "route --area 14,20,28,34"]), 0)
        text = self.read("out/route.txt")
        m = re.search(r"route --area 14,20,28,34: (\d+) nets there routed again, (\d+) outside "
                      r"stand as they are", text)
        self.assertIsNotNone(m, text)
        inside, outside = int(m.group(1)), int(m.group(2))
        self.assertEqual(inside + outside, 12)
        self.assertIn("stale     gear: routed again: in the area (route --area)", text)
        recs = design.read_all(self.out, "main")
        stood = [n for n, r in recs.items() if r["status"] == "kept"]
        self.assertEqual(len(stood), outside)
        for n in stood:                                  # exactly as they were
            self.assertEqual(sorted((e.x, e.y) for e in recs[n]["ents"]), before[n])
        self.assertEqual(main(["step", self.script, "route", "--with", "route --area 1,2,3"]), 2)

    def test_a_net_that_fails_keeps_the_route_that_stands(self):
        # route --failed keep (the default): paste and fix after, without losing a working belt
        from unittest import mock
        from fkcore import route
        from fkcore.__main__ import main
        self.build(to="route")
        had = len(design.read_all(self.out, "main")["gear"]["ents"])
        real = route._route_in

        def no_gear(cat, job, *a, **k):
            return (None, "no way (test)") if job.net == "gear" else real(cat, job, *a, **k)
        with mock.patch.object(route, "_route_in", no_gear):
            self.assertEqual(main(["step", self.script, "route", "gear"]), 0)
            self.assertIn(f"standing  gear: unrouted; its last route ({had} carriers) stands",
                          self.read("out/route.txt"))
            rec = design.read_all(self.out, "main")["gear"]
            self.assertEqual((rec["status"], len(rec["ents"])), ("unrouted", had))
            self.assertEqual(main(["step", self.script, "route", "gear", "--with",
                                   "route --failed drop --retry-failed always"]), 0)
        self.assertNotIn("standing  gear", self.read("out/route.txt"))
        self.assertEqual(design.read_all(self.out, "main")["gear"]["ents"], [])

    def test_route_try_asks_and_lays_nothing(self):
        # 3.0 `fk route --try A B`: a belt from A to B on the design as it stands; nothing changes
        from fkcore.__main__ import main
        self.build(to="route")
        before = {n: (r["status"], len(r["ents"])) for n, r in design.read_all(self.out, "main").items()}
        self.assertEqual(main(["step", self.script, "route", "--try", "0,52", "20,52"]), 0)
        text = self.read("out/route.txt")
        self.assertRegex(text, r"main: try 0,52 -> 20,52: \d+ carriers, .*nothing laid")
        self.assertIn("transport-belt 0.5,52.5", text)
        after = {n: (r["status"], len(r["ents"])) for n, r in design.read_all(self.out, "main").items()}
        self.assertEqual(after, before)
        self.assertEqual(main(["step", self.script, "route", "--try", "0,52", "x"]), 2)

    def test_unroute_routes_a_net_again(self):
        self.build(to="route")
        design.set_status(self.out, "main", "gear", "unrouted", design.UNROUTED_BY_YOU)
        self.build(to="route")
        self.assertIn("stale     gear: routed again: unrouted by you", self.read("out/route.txt"))
        self.assertEqual(design.read_all(self.out, "main")["gear"]["status"], "routed")


if __name__ == "__main__":
    unittest.main()
