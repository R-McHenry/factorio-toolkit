"""3.0, from the net walker's blueprints (WALKER-FINDINGS 4, items 6-8): a Literal entity whose
centre doesn't fit its size is snapped with a check line instead of stopping the build; a named
splitter or underground is a belt end; a seed may hold the net's inserters."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()


class _Literal(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkwalklessons-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, data):
        with open(os.path.join(self.dir, "lit.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def build(self, src):
        f = lang.parse(src, os.path.join(self.dir, "main.fk"))
        flat = elaborate(f, dict(f.modules), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat),
                              getattr(flat, "_port_edges", None))
        return flat, r, rep


class LiteralEndsTest(_Literal):
    def test_a_misplaced_centre_is_snapped_with_a_check(self):
        # an old blueprint's combinator half a tile off: 1x1 at (1.0, 2.0)
        self.write([{"name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4},
                    {"name": "constant-combinator", "x": 1.0, "y": 2.0}])
        flat, _r, _rep = self.build('lit = Literal<file="lit.json"> @(4, 4)\n')
        snaps = [c for c in flat.checks if c.code == "literal-snap"]
        self.assertEqual(len(snaps), 1)
        self.assertIn("constant-combinator at (1.0, 2.0)", snaps[0].msg)
        self.assertIn("placed at (1.5, 2.5)", snaps[0].msg)

    def test_a_named_underground_exit_drives_a_net(self):
        self.write({"entities": [
            {"name": "underground-belt", "x": 0.5, "y": 0.5, "direction": 4, "ug": "in"},
            {"name": "underground-belt", "x": 3.5, "y": 0.5, "direction": 4, "ug": "out"}],
            "names": {"entry": 0, "exit": 1}})
        flat, r, rep = self.build(
            'src = Chest<requester, item=iron-plate, rate=1/s> @(0, 8)\n'
            'lit = Literal<file="lit.json"> @(6, 8)\ngb = Chest<provider> @(18, 8)\n'
            "net i: src -> lit.entry\nnet o items iron-plate: lit.exit -> gb\n")
        self.assertEqual(r.failed, {})
        self.assertEqual((rep.nets["i"].status, rep.nets["o"].status),
                         ("connected", "connected"))

    def test_a_named_splitter_takes_a_net(self):
        self.write({"entities": [
            {"name": "splitter", "x": 0.5, "y": 1.0, "direction": 4},
            {"name": "transport-belt", "x": 1.5, "y": 0.5, "direction": 4},
            {"name": "transport-belt", "x": 1.5, "y": 1.5, "direction": 4}],
            "names": {"sp": 0}})
        flat, r, rep = self.build(
            'src = Chest<requester, item=iron-plate, rate=1/s> @(0, 8)\n'
            'lit = Literal<file="lit.json"> @(8, 8)\n'
            "net i: src -> lit.sp\n")
        self.assertIn("lit/splitter0", flat.machines)
        self.assertEqual(r.failed, {})
        self.assertEqual(rep.nets["i"].status, "connected")


class SeedHandsTest(_Literal):
    # a named assembler the router feeds by direct insertion (test_buffers' Literal): the seed
    # pins a belt under it and the inserter from that belt into it
    ENTS = [{"name": "transport-belt", "x": 0.5, "y": 0.5, "direction": 4},
            {"name": "assembling-machine-1", "x": 2.5, "y": 2.5, "recipe": "iron-gear-wheel"},
            {"name": "assembling-machine-1", "x": 6.5, "y": 2.5, "recipe": "iron-gear-wheel"},
            {"name": "small-electric-pole", "x": 9.5, "y": 0.5}]
    SRC = ("fein = Chest<requester, item=iron-plate, rate=1/s> @(0, 12)\n"
           'lit  = Literal<file="lit.json"> @(6, 4)\n'
           "net in: fein -> lit.asm2\n")

    def test_a_seeded_inserter_stands_and_feeds_its_machine(self):
        self.write({"entities": self.ENTS, "names": {"asm2": 2}})
        f = lang.parse(self.SRC, os.path.join(self.dir, "main.fk"))
        flat = elaborate(f, dict(f.modules), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        (key, rect), = route.jobs(flat, lay, CAT)["in"].taps
        x = rect[0] + 1                                  # under the machine's middle column
        seed = [fkp.Entity("~seed/0", "transport-belt", x + 0.5, rect[3] + 1.5, 4, {}),
                fkp.Entity("~seed/1", "inserter", x + 0.5, rect[3] + 0.5, 8, {})]
        r = route.route_layout(flat, lay, CAT, seeds={"in": seed})
        self.assertEqual(r.failed, {})
        hands = [(e.x, e.y) for e in r.layout.entities.values()        # into the machine
                 if e.attrs.get("net") == "in" and e.name.endswith("inserter")
                 and rect[0] - 1 <= e.x < rect[2] + 1 and rect[1] - 1 <= e.y < rect[3] + 1]
        self.assertEqual(hands, [(x + 0.5, rect[3] + 0.5)])
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual(rep.nets["in"].status, "connected")

    def test_a_seed_of_inserters_alone_is_refused(self):
        self.write({"entities": self.ENTS, "names": {"asm2": 2}})
        f = lang.parse(self.SRC, os.path.join(self.dir, "main.fk"))
        flat = elaborate(f, dict(f.modules), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT, seeds={"in": [
            fkp.Entity("~seed/0", "inserter", 12.5, 8.5, 8, {})]})
        self.assertIn("in", r.failed)
        self.assertIn("inserters alone", str(r.failed["in"]))


if __name__ == "__main__":
    unittest.main()
