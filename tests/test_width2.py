"""2.0.54: a net on both lanes of one belt. The router picks the grouping from where the buildings
stand (Rory, 2026-10-28: nothing prescribes it, and no Stack guides it): 24 electric furnaces
placed one by one, in one row or two facing rows, ore in and plates out at 15/s, each on one
yellow belt. And `lane L|R`, the lane a net ends on."""
import os
import shutil
import tempfile
import unittest

from fkcore import connect, expand, flow, fkp, lang, route, routed
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()


def furnace_line(two_sided):
    """24 electric furnaces placed one by one; six ore chests; six gear assemblers take 15/s."""
    rows, names = [], []
    for k in range(24):
        x, y = (12 + 3 * (k % 12), 14 if k < 12 else 24) if two_sided else (12 + 3 * k, 14)
        rows.append(f"f{k} = Furnace<recipe=iron-plate, machine=electric-furnace> @({x}, {y})")
        names.append(f"f{k}")
    rows += [f"ore{j} = Chest<requester, item=iron-ore, rate=2.5/s> @(2, {4 + 4 * j})"
             for j in range(6)]
    rows += ["gears = AsmRow<n=6, recipe=iron-gear-wheel, machine=assembling-machine-2> @(30, 40)",
             "box1 = Chest<provider> @(60, 46)", "box2 = Chest<provider> @(64, 46)",
             "box3 = Chest<provider> @(68, 46)",
             "net ore_: " + ", ".join(f"ore{j}" for j in range(6)) + " -> " + ", ".join(names),
             "net plates: " + ", ".join(names) + " -> gears",
             "net g: gears -> box1, box2, box3"]
    return "\n".join(rows) + "\n"


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def routed_of(text):
    flat = flat_of(text)
    lay, _notes = expand.expand_factory(flat, CAT)
    r = route.route_layout(flat, lay, CAT)
    return flat, r, routed.solve(flat, r.layout, CAT)


def got(rr, net, item):
    keys = {k for k, _i in rr.flat.nets[net].consumers}
    return sum(rr.res.delivered.get((k, ""), {}).get(item, 0.0) for k in keys)


def lanes_used(rr, net, item):
    return {nid[1] for nid, node in rr.lg.nodes.items()
            if node.kind == "lane" and nid[0].startswith(f"~{net}/")
            and rr.res.flow.get(nid, {}).get(item, 0.0) > 1e-9}


class _Line:
    TWO = None

    @classmethod
    def setUpClass(cls):
        cls.flat, cls.r, cls.rr = routed_of(furnace_line(cls.TWO))

    def test_connects(self):
        self.assertEqual(self.r.failed, {})
        rep = connect.connect(self.r.layout, CAT, connect.endpoints(self.flat))
        self.assertEqual({n for n, x in rep.nets.items() if x.status != "connected"}, set())
        self.assertEqual(rep.leaks, [])

    def test_a_group_onto_each_lane(self):
        for net in ("ore_", "plates"):
            line = next(l for l in self.r.lines if l.split()[1] == f"{net}:")
            self.assertIn("(a group of drivers onto each lane)", line)

    def test_fifteen_a_second_on_one_yellow_belt(self):
        self.assertAlmostEqual(got(self.rr, "ore_", "iron-ore"), 15.0, places=3)
        self.assertAlmostEqual(got(self.rr, "plates", "iron-plate"), 15.0, places=3)
        self.assertEqual(lanes_used(self.rr, "plates", "iron-plate"), {"L", "R"})
        thin = [str(c) for c in routed.report(self.rr)[1] if c.code == "too-thin"
                and ("lanes" in str(c) or "splitters" in str(c))]
        self.assertEqual(thin, [])


class OneSidedLineTest(_Line, unittest.TestCase):
    """One row: every furnace on the same side of whatever belt runs past it."""
    TWO = False


class TwoSidedLineTest(_Line, unittest.TestCase):
    """Two rows facing each other."""
    TWO = True


class RebuildTest(unittest.TestCase):
    """A rebuild with nothing changed keeps a width-2 route as it stands (the tail past a pickup
    a first route can leave is taken up before it is committed)."""

    def test_kept_byte_for_byte(self):
        d = tempfile.mkdtemp(prefix="fkw2-")
        try:
            with open(os.path.join(d, "line.fk"), "w", encoding="utf-8") as fh:
                fh.write(furnace_line(False))
            with open(os.path.join(d, "lab.surface"), "w", encoding="utf-8") as fh:
                fh.write("surface  lab\nmode     lab\nterrain  none\ncatalog  base\n"
                         "place line = line plot 780,452 90x60\n")
            with open(os.path.join(d, "lab.build.fkb"), "w", encoding="utf-8") as fh:
                fh.write("read_surface lab\nread_terrain none\nelaborate\nsize\n"
                         "place --keep pinned\nroute --only stale --effort normal\n"
                         "cover power --pole medium-electric-pole\nfloorplan\n"
                         "report_checks\nwrite_layout\n")
            script = os.path.join(d, "lab.build.fkb")
            code, ctx = flow.run(script, cat=CAT, echo=lambda _l: None)
            self.assertEqual(code, 0, ctx.log)
            first = open(os.path.join(d, "line.fkp"), encoding="utf-8").read()
            code, ctx = flow.run(script, cat=CAT, echo=lambda _l: None)
            self.assertEqual(code, 0, ctx.log)
            self.assertEqual(open(os.path.join(d, "line.fkp"), encoding="utf-8").read(), first)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class LanePinTest(unittest.TestCase):
    TEXT = """
        ore   = Chest<requester, item=iron-ore, rate=2/s> @(2, 2)
        smelt = SmelterRow<n=4, recipe=iron-plate, machine=electric-furnace> @(8, 2)
        gears = AsmRow<n=2, recipe=iron-gear-wheel> @(8, 20)
        box   = Chest<provider> @(2, 30)
        net o: ore -> smelt
        net plates{pin}: smelt -> gears
        net g: gears -> box
    """

    def lane_at_the_row(self, pin):
        flat, r, rr = routed_of(self.TEXT.format(pin=pin))
        self.assertEqual(r.failed, {})
        on = {nid[1] for nid in (("gears/in1b0", "L"), ("gears/in1b0", "R"))
              if rr.res.flow.get(nid, {}).get("iron-plate", 0.0) > 1e-9}
        return on, r

    def test_left_and_right(self):
        for pin in ("L", "R"):
            on, r = self.lane_at_the_row(f" lane {pin}")
            self.assertEqual(on, {pin})
            line = next(l for l in r.lines if l.split()[1] == "plates:")
            self.assertIn(f"lane {pin})", line)
            stubs = [e for k, e in r.layout.entities.items() if k.startswith("~plates/z")]
            self.assertEqual(len(stubs), 1)


class SyntaxAndChecksTest(unittest.TestCase):
    def test_parsed(self):
        net = lang.parse("net p items iron-plate width 2 lane L limited: a -> b",
                         "t.fk").body.nets[0]
        self.assertEqual((net.width, net.lane, net.limited), (2, "L", True))

    def test_refused(self):
        for text in ("net p width 3: a -> b", "net p lane X: a -> b"):
            with self.assertRaises(lang.ParseError if hasattr(lang, "ParseError") else Exception):
                lang.parse(text, "t.fk")

    def test_one_driver(self):
        flat = flat_of("""
            ore   = Chest<requester, item=iron-ore, rate=2/s> @(2, 2)
            smelt = SmelterRow<n=4, recipe=iron-plate, machine=electric-furnace> @(8, 2)
            box   = Chest<provider> @(2, 30)
            net o: ore -> smelt
            net p width 2: smelt -> box
        """)
        lines = [str(c) for c in flat.checks if c.code == "width"]
        self.assertEqual(len(lines), 1)
        self.assertIn("width 2 with one driver, smelt", lines[0])

    def test_a_pair_cannot_be_wide(self):
        with self.assertRaises(Exception) as ctx:
            flat_of("""
                a = Chest<requester, item=iron-ore, rate=2/s> @(2, 2)
                b = Chest<requester, item=coal, rate=2/s> @(2, 6)
                s = SmelterRow<n=2, recipe=iron-plate> @(8, 2)
                net o width 2: a -> s
                net f: b -> s
                lanes o | f
            """)
        self.assertIn("width 2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
