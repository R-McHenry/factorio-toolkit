"""2.0.38 (PLAN-MODULES phase 4): every sealed module's generated contract.

The bus base with four ribs prints four lines: each rib's iron in (where it crosses, what it got) and
its gears out (where they go, what it made). A starved rib shows (got 0.0) against its 2.0/s
contract; a portless module has no contract line.
"""
import unittest

from fkcore import contract, lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

RIB = """
module GearRib size 16x10 {
  port iron : in iron-plate @w
  port gear : out iron-gear-wheel @e
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(2, 1)
  net fe: iron -> g
  net g: g -> gear
}
"""

BASE = RIB + """
feed = Chest<requester, item=iron-plate, rate=RATE> @(0, 20)
bus  = Bus<belts=4, item=iron-plate>(in1: feed, r0: rib0.iron, r1: rib1.iron,
                                     r2: rib2.iron, r3: rib3.iron) @(10, 20)
rib0 = GearRib @(2, 5)
rib1 = GearRib @(22, 5)
rib2 = GearRib @(42, 5)
rib3 = GearRib @(62, 5)
box0 = Chest<provider, limit=8> @(19, 10)
box1 = Chest<provider, limit=8> @(39, 10)
box2 = Chest<provider, limit=8> @(59, 10)
box3 = Chest<provider, limit=8> @(79, 10)
net g0: rib0.gear -> box0
net g1: rib1.gear -> box1
net g2: rib2.gear -> box2
net g3: rib3.gear -> box3
"""

PLAIN = """
module GearRib {
  c = Chest<requester, item=iron-plate, rate=2> @(0, 0)
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(4, 0)
  b = Chest<provider, limit=8> @(20, 0)
  net fe: c -> g
  net g: g -> b
}
rib = GearRib @(0, 0)
"""


def lines_of(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    return contract.contract(flat, rates.solve(flat))


class ContractTest(unittest.TestCase):
    def test_every_rib_has_its_in_and_out(self):
        lines = lines_of(BASE.replace("RATE", "16"))
        self.assertEqual(len(lines), 4)
        # 2.0.46: each tap in front of its rib's west port (ribs at x 2, 22, 42, 62; the bus at 10),
        # the first two held back by the band before them
        for i, (line, tap) in enumerate(zip(lines, (7, 13, 32, 52))):
            self.assertTrue(line.startswith(f"rib{i}: "), line)
            self.assertIn(f"in iron-plate 2.0/s via bus tap n{tap} (got 2.0)", line)
            self.assertIn(f"out iron-gear-wheel 1.0/s via box{i}/c0 (got 1.0)", line)

    def test_a_starved_rib_shows_what_it_got(self):
        lines = lines_of(BASE.replace("RATE", "2"))
        self.assertEqual(len(lines), 4)
        got = []
        for line in lines:
            chunk = line.split("in iron-plate 2.0/s via bus tap ")[1]
            got.append(float(chunk.split("(got ")[1].split(")")[0]))
        self.assertTrue(all(g < 2.0 for g in got), got)
        self.assertAlmostEqual(sum(got), 2.0, places=6)

    def test_a_portless_module_has_no_contract(self):
        self.assertEqual(lines_of(PLAIN), [])

    def test_the_example_in_the_docs_prints_four_ribs(self):
        from pathlib import Path
        here = Path(__file__).resolve().parents[1]
        text = (here / "agent" / "docs" / "examples" / "bus4ribs.fk").read_text(encoding="utf-8")
        lines = lines_of(text)
        self.assertEqual(len(lines), 4)
        self.assertIn("via bus tap n7 (got 2.0)", lines[0])
        self.assertIn("via bus tap n52 (got 2.0)", lines[3])     # 2.0.46: in front of rib3


if __name__ == "__main__":
    unittest.main()
