"""2.0.28 (PLAN-MODULES phase 1): ports on module definitions.

A module that declares a ``port`` is sealed: its nets are local, the rest of the design reaches it
only by a port's name, and a ref that reaches past them is refused at elaboration. A module with no
port is exactly what it was before — which is every existing design, and the baseline test below is
the proof: it re-elaborates every ``.fk`` in the repository and compares the digest of what 2.0.27
(elaboration-baseline.json, generated from this tree before the change) produced.

Regenerate the baseline only when a change to elaboration is *meant* to show: a new check, a new
template. A ports release that changes it has broken the migration promise.
"""
import hashlib
import json
import os
import unittest

from fkcore import expand, lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate, elaborate_file

CAT = Catalog.load()
DATA = os.path.join(os.path.dirname(__file__), "data")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RIB = """
module GearRib size 24x10 {
  port iron : in  iron-plate @w
  port gear : out iron-gear-wheel @w
  gears = AsmRow<n=2, recipe=iron-gear-wheel> @(4, 2)
  net fe: iron -> gears
  net g:  gears -> gear
}
"""

FEED = """
feed  = Chest<requester, item=iron-plate, rate=10> @(0, 0)
rib   = GearRib @(10, 10)
box   = Chest<provider, limit=8> @(30, 10)
net ore: feed -> rib.iron
net gear_out: rib.gear -> box
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def digest(flat):
    """What the baseline records: every machine, every net and every check line, hashed."""
    machines = {k: {"prototype": m.prototype, "recipe": m.recipe,
                    "needs": dict(sorted(m.needs.items())),
                    "makes": dict(sorted(m.makes.items())),
                    "takes": None if m.takes is None else sorted(m.takes),
                    "sink": m.sink, "drain": m.drain, "source": m.source, "duty": m.duty,
                    "inst": m.inst, "kind": m.kind, "extra": dict(sorted(m.extra.items()))}
                for k, m in sorted(flat.machines.items())}
    nets = {n: {"items": list(v.items), "drivers": [list(d) for d in v.drivers],
                "consumers": [list(c) for c in v.consumers], "declared": v.declared,
                "limited": v.limited} for n, v in sorted(flat.nets.items())}
    checks = sorted([c.code, c.where, c.msg] for c in flat.checks)
    body = {"machines": machines, "nets": nets, "checks": checks}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest(), len(machines), len(nets), len(checks)


def codes(flat):
    return [c.code for c in flat.checks]


class BaselineTest(unittest.TestCase):
    """Every existing .fk elaborates identically to 2.0.27's elaboration."""

    def test_every_existing_design_elaborates_identically(self):
        with open(os.path.join(DATA, "elaboration-baseline.json"), encoding="utf-8") as fh:
            baseline = json.load(fh)["designs"]
        self.assertGreater(len(baseline), 30)          # the corpus did not shrink silently
        for rel, want in sorted(baseline.items()):
            with self.subTest(rel):
                flat = elaborate_file(os.path.join(ROOT, rel), CAT)
                sha, nm, nn, nc = digest(flat)
                self.assertEqual((nm, nn, nc), (want["machines"], want["nets"], want["checks"]),
                                 f"{rel}: machines/nets/checks changed")
                self.assertEqual(sha, want["sha256"], f"{rel}: its elaboration changed")


class SyntaxTest(unittest.TestCase):
    def test_port_and_size(self):
        m = lang.parse(RIB, "t.fk").modules["GearRib"]
        self.assertEqual(m.size, (24, 10))
        self.assertEqual([(p.name, p.dir, p.items, p.side, p.pos) for p in m.ports],
                         [("iron", "in", ["iron-plate"], "w", None),
                          ("gear", "out", ["iron-gear-wheel"], "w", None)])

    def test_a_pinned_tile_and_a_lane_pair(self):
        m = lang.parse("module M size 8x6 {\n"
                       "  port feed : in iron-ore | coal @s5\n"
                       "  port out_ : out iron-plate, copper-plate @n0\n"
                       "}", "t.fk").modules["M"]
        self.assertEqual([(p.items, p.side, p.pos) for p in m.ports],
                         [(["iron-ore", "coal"], "s", 5),
                          (["iron-plate", "copper-plate"], "n", 0)])

    def test_a_port_belongs_to_a_module(self):
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse("port x : in iron-plate @w\na = AsmRow<n=1, recipe=pipe>", "t.fk")
        self.assertIn("a port is a module's interface", str(cm.exception))

    def test_malformed_ports(self):
        for text, msg in (("module M { port x : sideways iron-plate @w }", "in, out or inout"),
                          ("module M { port x : in iron-plate @q }", "side is n, e, s or w"),
                          ("module M { port x : in iron-plate w }", "expected '@'"),
                          ("module M size 24 { }", "size WxH")):
            with self.assertRaises(lang.FkSyntaxError) as cm:
                lang.parse(text, "t.fk")
            self.assertIn(msg, str(cm.exception))


class SealedTest(unittest.TestCase):
    def test_a_crossing_net_splits_at_the_port(self):
        flat = flat_of(RIB + FEED)
        self.assertEqual(flat.sealed, {"rib"})
        self.assertEqual(flat.nets["ore"].scope, "")
        self.assertEqual(flat.nets["ore"].consumers, [("rib/iron", "iron-plate")])
        self.assertEqual(flat.nets["rib/fe"].scope, "rib")
        self.assertEqual(flat.nets["rib/fe"].drivers, [("rib/iron", "iron-plate")])
        self.assertEqual(flat.nets["rib/g"].consumers, [("rib/gear", "iron-gear-wheel")])
        self.assertEqual(flat.nets["gear_out"].drivers, [("rib/gear", "iron-gear-wheel")])
        self.assertEqual(codes(flat), [])                  # a limited chest: nothing to warn

    def test_rates_see_one_net_through_the_port(self):
        flat = flat_of(RIB + FEED)
        model = rates.solve(flat)
        self.assertEqual(model.pools[("rib/fe", "iron-plate")], ("ore", "iron-plate"))
        self.assertEqual(rates.underfed(model), [])
        self.assertAlmostEqual(model.util["rib/gears/m0"], 1.0)   # fed through the port
        self.assertAlmostEqual(model.nets[("ore", "iron-plate")].delivered, 4.0, places=6)

    def test_a_ref_past_the_ports_is_refused_with_the_port_to_add(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + FEED.replace("rib.iron", "rib.gears"))
        msg = str(cm.exception)
        self.assertIn("rib.gears", msg)
        self.assertIn("is a sealed module (GearRib)", msg)
        self.assertIn("iron (in iron-plate)", msg)          # the ports it does have
        self.assertIn("gear (out iron-gear-wheel)", msg)
        self.assertIn("port NAME : in ITEM @SIDE", msg)      # the line to add, as a consumer

    def test_a_bare_ref_or_a_star_is_refused(self):
        for ref in ("rib", "rib.*"):
            with self.assertRaises(ElabError) as cm:
                flat_of(RIB + FEED.replace("rib.iron", ref))
            self.assertIn("is a sealed module (GearRib)", str(cm.exception))

    def test_a_port_has_no_inside(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + FEED.replace("rib.iron", "rib.iron.deep"))
        self.assertIn("nothing is inside it", str(cm.exception))

    def test_a_sealed_module_is_per_instance(self):
        flat = flat_of(RIB + """
a = GearRib @(0, 0)
b = GearRib @(40, 0)
feed = Chest<requester, item=iron-plate, rate=4> @(30, 20)
box = Chest<provider> @(60, 20)
net x: feed -> a.iron, b.iron
net y: a.gear -> box
net z: b.gear -> box
""")
        self.assertEqual(sorted(flat.ports), ["a/gear", "a/iron", "b/gear", "b/iron"])
        self.assertEqual(sorted(flat.sealed), ["a", "b"])
        self.assertEqual(sorted(flat.nets["x"].consumers),
                         [("a/iron", "iron-plate"), ("b/iron", "iron-plate")])
        self.assertEqual(flat.nets["y"].drivers, [("a/gear", "iron-gear-wheel")])

    def test_through_a_transparent_module(self):
        flat = flat_of("""
module Rib size 10x6 {
  port in_ : in iron-plate @w
  port out_ : out iron-gear-wheel @e
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(1, 1)
  net fe: in_ -> g
  net gg: g -> out_
}
module Shell { inner = Rib @(2, 2) }
sh = Shell @(0, 0)
feed = Chest<requester, item=iron-plate, rate=2> @(20, 0)
box = Chest<provider> @(30, 0)
net a: feed -> sh.inner.in_
net b: sh.inner.out_ -> box
""")
        self.assertEqual(flat.sealed, {"sh/inner"})
        self.assertEqual(flat.nets["a"].consumers, [("sh/inner/in_", "iron-plate")])
        self.assertEqual(flat.nets["sh/inner/fe"].drivers, [("sh/inner/in_", "iron-plate")])

    def test_a_transparent_module_still_reaches_its_machines(self):
        flat = flat_of("""
module M { a = AsmRow<n=1, recipe=pipe> }
m = M
c = Chest<provider> @(20, 0)
net p: m.a -> c
""")
        self.assertEqual(flat.sealed, set())
        self.assertEqual(flat.ports, {})
        self.assertEqual(flat.nets["p"].drivers, [("m/a/m0", "pipe")])

    def test_an_instance_may_not_take_a_port_name(self):
        with self.assertRaises(ElabError) as cm:
            flat_of("module M {\n  port a : in iron-plate @w\n  a = AsmRow<n=1, recipe=pipe>\n}\n"
                    "m = M")
        self.assertIn("is a port of module M", str(cm.exception))

    def test_a_port_declared_twice(self):
        with self.assertRaises(ElabError) as cm:
            flat_of("module M {\n  port a : in iron-plate @w\n  port a : out iron-plate @w\n}\n"
                    "m = M")
        self.assertIn("port a is defined twice", str(cm.exception))


class PortCheckTest(unittest.TestCase):
    def ports(self, text):
        return [c for c in flat_of(text).checks if c.code == "PORT"]

    def test_a_port_no_net_names(self):
        text = (RIB + FEED).replace("net ore: feed -> rib.iron\n", "") \
                          .replace("net fe: iron -> gears\n", "")
        checks = self.ports(text)
        self.assertEqual(len(checks), 1)
        self.assertIn("no net names it", checks[0].msg)

    def test_a_port_no_net_outside_uses(self):
        checks = self.ports(RIB + FEED.replace("net ore: feed -> rib.iron\n", ""))
        self.assertEqual(len(checks), 1)                   # one line, not a per-item one too
        self.assertIn("no net outside rib uses it", checks[0].msg)

    def test_against_its_direction(self):
        checks = self.ports(RIB + FEED + "net back: rib.iron -> box\n")
        msgs = " ".join(c.msg for c in checks)
        self.assertIn("used against its direction (in)", msgs)
        self.assertIn("net back drives it outside", msgs)

    def test_items_that_disagree(self):
        checks = self.ports(RIB + FEED.replace("net ore: feed -> rib.iron",
                                               "net ore items copper-plate: feed -> rib.iron"))
        self.assertEqual(len(checks), 1)                    # one line, not a dead-port one too
        self.assertIn("net ore carries copper-plate", checks[0].msg)
        self.assertIn("port iron is in iron-plate", checks[0].msg)

    def test_an_item_nothing_outside_brings(self):
        checks = self.ports("""
module Burner size 8x6 {
  port feed : in iron-ore | coal @s
  row = SmelterRow<n=1, recipe=iron-plate> @(1, 1)
  net ore_: feed -> row
}
mine = MinerRow<n=1, resource=iron-ore> @(0, 0)
burn = Burner @(10, 0)
net feed: mine -> burn.feed
""")
        self.assertEqual([c.msg for c in checks], ["nothing outside brings coal to it"])

    def test_a_tile_off_the_frame(self):
        checks = self.ports(RIB.replace("@w\n  port gear", "@n30\n  port gear") + FEED)
        msgs = " ".join(c.msg for c in checks)
        self.assertIn("@n30 is off the module's frame", msgs)
        self.assertIn("GearRib is 24x10, so its n edge runs 0..23", msgs)


class FrameTest(unittest.TestCase):
    def test_a_declared_size_is_the_frame(self):
        flat = flat_of("""
module Rib size 10x6 { g = AsmRow<n=1, recipe=pipe> @(1, 1) }
r = Rib @(20, 20)
""")
        self.assertEqual(expand._module_frame(flat, "r", CAT), (0, 0, 10, 6))

    def test_a_module_without_size_still_measures_its_children(self):
        flat = flat_of("""
module Rib { c = Chest<provider> @(1, 1) }
r = Rib @(20, 20)
""")
        self.assertEqual(flat.insts["r"].size, None)
        x0, y0, x1, y1 = expand._module_frame(flat, "r", CAT)
        self.assertEqual((x0, y0), (0, 0))
        self.assertGreater(x1, 1)                      # the chest's own frame
        self.assertGreater(y1, 1)


if __name__ == "__main__":
    unittest.main()
