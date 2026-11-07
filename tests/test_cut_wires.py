"""2.1.33 (lab FRICTION 20): a captured wire between two Literals cut from one file is laid again
when both stand as the capture did. The demo's green wire from the petroleum chest to the hub
sorter's combinator crossed the E1/E2 cut, and the hub train made 141 visits without unloading."""
import os
import shutil
import tempfile
import unittest

from fkcore import circuits, codec, expand, lang
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()


class CutWireTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        rows = [{"name": "iron-chest", "x": 0.5, "y": 0.5, "direction": None, "attrs": {}},
                {"name": "arithmetic-combinator", "x": 5.5, "y": 1.0, "direction": 0,
                 "attrs": {}},
                {"name": "small-lamp", "x": 6.5, "y": 0.5, "direction": None, "attrs": {}}]
        green = codec.connector("green")
        links = [(0, green, 1, green),                       # chest -> combinator input
                 (1, codec.connector("red", "out"), 2, codec.connector("red"))]   # inside B
        with open(os.path.join(self.dir, "cap.txt"), "w") as fh:
            fh.write(codec.blueprint(rows, links=links))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def lay(self, b_at):
        src = ('a = Literal<file="cap.txt", box="0,0,3,3"> @(10, 10)\n'
               f'b = Literal<file="cap.txt", box="3,0,8,3"> @{b_at}\n')
        f = lang.parse(src, os.path.join(self.dir, "t.fk"))
        flat = elaborate(f, dict(f.modules), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        return circuits.lay(flat, lay, CAT)

    def test_lined_up_the_wire_comes_back(self):
        out, lines, checks = self.lay("(13, 10)")
        cut = [(w.colour, w.a, w.b) for w in out.wires if w.net.startswith("cut/")]
        self.assertEqual(cut, [("green", "a/iron-chest0", "b/arithmetic-combinator0.in")])
        self.assertIn("wire cut/cap.txt: 1 captured wire across Literal cuts, laid as the capture "
                      "had them", lines)
        self.assertEqual([c for c in checks if c.code == "wire-cut"], [])

    def test_moved_apart_it_is_named(self):
        out, _lines, checks = self.lay("(20, 10)")
        self.assertEqual([w for w in out.wires if w.net.startswith("cut/")], [])
        msgs = [c.msg for c in checks if c.code == "wire-cut"]
        self.assertEqual(len(msgs), 1)
        self.assertIn("a/iron-chest0 to b/arithmetic-combinator0", msgs[0])


if __name__ == "__main__":
    unittest.main()
