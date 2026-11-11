"""The bootstrap stages' FRICTION.md (lab-session\\fk-boot-w3, 11-11): checks that were missing.

- ``crowded-ends``: six nets ended at one 1x1 chest and two came back ``no-route ... 0 segments``
  with no reason; a 1x1 entity has four side tiles for hands.
- ``report_bom`` says which items nothing built in the design makes (the stages ran on the kit's
  long-handed inserters until they ran out)."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import flow, lang
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def gears_into_one_chest(n):
    return "box = Chest<provider> @(10, 10)\n" + "".join(
        f"a{i} = Assembler<recipe=iron-gear-wheel> @({i * 5}, 0)\nnet n{i}: a{i} -> box\n"
        for i in range(n))


class CrowdedEndsTest(unittest.TestCase):
    def test_six_nets_into_a_chest_is_said(self):
        got = [str(c) for c in flat_of(gears_into_one_chest(6)).checks
               if c.code == "crowded-ends"]
        self.assertEqual(len(got), 1)
        self.assertIn("6 nets end at this 1x1 passive-provider-chest", got[0])
        self.assertIn("4 side tiles", got[0])
        self.assertIn("one sushi belt can carry them all", got[0])

    def test_the_sushi_merge_is_given_and_routes(self):
        # Rory 11-11: check that there is an easy way to merge them into a sushi net into the chest
        recipes = ["iron-gear-wheel", "copper-cable", "iron-stick", "iron-gear-wheel",
                   "copper-cable", "pipe"]
        head = "box = Chest<provider> @(14, 12)\n" + "".join(
            f"a{i} = Assembler<recipe={r}> @({i * 5}, 0)\n" for i, r in enumerate(recipes))
        src = head + "".join(f"net n{i}: a{i} -> box\n" for i in range(6))
        (c,) = [c for c in flat_of(src).checks if c.code == "crowded-ends"]
        line = str(c).split("`")[1]
        self.assertEqual(line, "net n0 items iron-gear-wheel, copper-cable, iron-stick, pipe: "
                               "a0, a1, a2, a3, a4, a5 -> box")
        from fkcore import connect, expand, route
        flat = flat_of(head + line + "\n")
        self.assertFalse([c for c in flat.checks if c.code == "crowded-ends"])
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual(rep.nets["n0"].status, "connected")

    def test_four_fit(self):
        self.assertFalse([c for c in flat_of(gears_into_one_chest(4)).checks
                          if c.code == "crowded-ends"])


class NoMakerBomTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkbootfr-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        files = {
            "t.fk": "src = Chest<requester, item=iron-plate, rate=1/s> @(0, 2)\n"
                    "gear = Assembler<recipe=iron-gear-wheel> @(12, 2)\n"
                    "dst = Chest<provider> @(24, 2)\n"
                    "net fe: src -> gear\nnet g: gear -> dst\n",
            "nauvis.surface": "surface nauvis\nterrain none\nplace t = t plot 0,0 34x10\n",
            "stock.json": json.dumps({"transport-belt": 100, "fast-inserter": 1}),
            "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\n"
                                "place --keep pinned\nroute --only stale\nfloorplan\n"
                                "report_bom --stock stock.json\nwrite_layout\n"}
        for name, text in files.items():
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

    def test_the_bill_says_what_nothing_makes(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        with open(os.path.join(self.dir, "out", "report_bom.txt"), encoding="utf-8") as fh:
            bom = fh.read()
        self.assertRegex(bom, r"fast-inserter +\d+  have 1  no maker")
        self.assertIn("items come only from stock or the network", bom)
        short = [str(c) for _s, c in ctx.checks if c.code == "short-stock" and c.where == "fast-inserter"]
        self.assertTrue(short and "nothing built in the design makes it" in short[0])


class PortFeedTest(unittest.TestCase):
    """A route's last belt beside a port's belt, facing the way it came, is no feed (Sci's cu port:
    ``~w_cu/b271`` E under ``~sci/s_cu/b0`` N, counted connected, and Sci never saw copper)."""

    def graph_of(self, outside_dir):
        from fkcore import connect, expand, fkp
        lay = fkp.loads("fkp 1 factory t\n"
                        f"e ~w/b0 transport-belt 0.5,1.5 {outside_dir} net=w\n"
                        "e sci/b0 transport-belt 0.5,0.5 N net=s\n")
        port = expand.PortEdge(inside=(0, 0), outside=(0, 1), src=(0, 1), dst=(0, 0))
        return connect.graph(lay, CAT, {"sci.cu": port})

    def test_a_belt_heading_into_the_port_feeds_it(self):
        g = self.graph_of("N")
        self.assertIn(("sci.cu", "belt"), set(g.succ.get("~w/b0", ())))
        self.assertIn(("sci/b0", "belt"), set(g.succ.get("sci.cu", ())))

    def test_a_belt_facing_past_the_port_does_not(self):
        g = self.graph_of("E")
        self.assertNotIn("sci.cu", {k for k, _v in g.succ.get("~w/b0", ())})
        self.assertIn(("sci/b0", "belt"), set(g.succ.get("sci.cu", ())))   # its own side stands


if __name__ == "__main__":
    unittest.main()
