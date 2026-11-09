"""45-pairports: a pair already on one belt whose two ends are ports routes like any belt.

A river's tap leaves its mouth as one belt of two items, a lane each (a `PairM` joins them), and
goes to a port of the core; nothing hands on or off it on the way. Before this, such a pair was
held to the stack cell's rule (2.0.48: a pair that comes in paired runs straight on past every
machine), and every tap of the megabelt flower failed with "no straight belt runs on from there".
Now a paired pair with no machine on the way routes as one plain net from where it comes in: any
belt keeps both lanes.
"""
import unittest

from fkcore import connect
from tests.test_stacks import flat_of, routed, CAT

PAIR = """
module PairM<a, b> size 8x6 {
  port a_in : in  $a @n1
  port b_in : in  $b @n5
  port p    : out $a | $b @s3
  net x items $a: a_in -> p
  net y items $b: b_in -> p
  lanes x | y
}
# a tap's end: the pair runs straight past two chests to an end port (corecells.fk's TapArm)
module Arm<a, b> size 7x7 {
  port t     : in  $a | $b @n3
  port t_out : out $a | $b @s3
  ca = Chest<provider, limit=4> @(1, 3)
  cb = Chest<provider, limit=4> @(5, 3)
  net na items $a: t -> ca, t_out
  net nb items $b: t -> cb, t_out
  lanes na | nb
}
fe = Chest<requester, item=iron-plate, rate=4> @(1, 0)
cu = Chest<requester, item=copper-plate, rate=4> @(9, 0)
pm = PairM<a=iron-plate, b=copper-plate> @(2, 4)
arm = Arm<a=iron-plate, b=copper-plate> @(30, 24)
net ffe: fe -> pm.a_in
net fcu: cu -> pm.b_in
net ta items iron-plate: pm.p -> arm.t
net tb items copper-plate: pm.p -> arm.t
lanes ta | tb
"""


class PairPortsTest(unittest.TestCase):
    def test_a_paired_pair_between_two_ports_routes_round_corners(self):
        flat = flat_of(PAIR)
        r = routed(flat)
        self.assertEqual(r.failed, {})
        line = next(ln for ln in r.lines if ln.startswith("routed    ta|tb"))
        self.assertIn("both lanes on one belt from its paired port", line)
        belts = [e for e in r.layout.entities.values()
                 if e.attrs.get("net") == "ta|tb" and e.name in ("transport-belt", "underground-belt")]
        self.assertGreater(len(belts), 20)                 # 28 tiles east and 14 south, no straight line
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
        self.assertEqual(rep.leaks, [])
        self.assertTrue(all(n.connected for n in rep.nets.values()),
                        [k for k, n in rep.nets.items() if not n.connected])


if __name__ == "__main__":
    unittest.main()
