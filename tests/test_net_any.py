"""3.0 (Rory, 2026-11-01, from the reverse-engineering results): ``net NAME any:`` is connected when
each driver reaches some consumer and each consumer is reached, not every driver every consumer: a
belt that passes through a module, an output that splits. It changes the check, not the route."""
import unittest
from types import SimpleNamespace

from fkcore import fkp, lang
from fkcore.catalog import Catalog
from fkcore.connect import connect

CAT = Catalog.load()

# one belt east; c1 loads at its head, x1 takes off it, c2 loads after x1, x2 takes at its end:
# c2 never reaches x1
LINE = """fkp 1 factory t
e c/c1 iron-chest 0.5,2.5
e i/c1 inserter 0.5,1.5 S net=a
e c/x1 iron-chest 1.5,-1.5
e i/x1 inserter 1.5,-0.5 S net=a
e c/c2 iron-chest 3.5,2.5
e i/c2 inserter 3.5,1.5 S net=a
e c/x2 iron-chest 5.5,-1.5
e i/x2 inserter 5.5,-0.5 S net=a
""" + "".join(f"e a/b{i} transport-belt {i + 0.5},0.5 E net=a\n" for i in range(6))


def net(any_):
    return SimpleNamespace(nets={"a": SimpleNamespace(
        drivers=[("c/c1", "iron-plate"), ("c/c2", "iron-plate")],
        consumers=[("c/x1", "iron-plate"), ("c/x2", "iron-plate")], width=1, any=any_)})


class NetAnyTest(unittest.TestCase):
    def test_parses(self):
        f = lang.parse("a = Chest<plain> @(0, 0)\nb = Chest<plain> @(4, 0)\n"
                       "net n items iron-plate any: a -> b\nnet m: a -> b\n", "t.fk")
        nets = {n.name: n for n in f.body.nets}
        self.assertTrue(nets["n"].any)
        self.assertFalse(nets["m"].any)

    def test_every_pair_without_it(self):
        r = connect(fkp.loads(LINE), CAT, net(False)).nets["a"]
        self.assertEqual((r.reached, r.pairs), (3, 4))
        self.assertEqual(r.unreached, [("c/c2", "c/x1")])

    def test_each_end_with_it(self):
        r = connect(fkp.loads(LINE), CAT, net(True)).nets["a"]
        self.assertEqual(r.unreached, [])


if __name__ == "__main__":
    unittest.main()
