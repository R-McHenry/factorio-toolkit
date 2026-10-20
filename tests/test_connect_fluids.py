"""Connectivity of fluid nets (fkcore.connect over fluid boxes): joins as the game makes them,
per fluid net connected yes/no, and fluid LEAKs. Directions follow the .fkp; a pipe-to-ground
faces its open side."""
import os
import unittest

from fkcore import connect, fkp
from fkcore.catalog import Catalog

CAT = Catalog.load()
PLANT = os.path.join(os.path.dirname(__file__), "..", "games", "nauvis", "plant.fkp")


def L(text, name="t"):
    return fkp.loads(f"fkp 1 factory {name}\n" + "\n".join(l.strip() for l in text.splitlines()))


class FluidConnectTest(unittest.TestCase):
    PUMP_TO_CHEM = """
        e w/pump offshore-pump 1.5,0.5 N rate=1200
        e ~w/p0 pipe 1.5,1.5 net=w
        e ~w/p1 pipe 1.5,2.5 net=w
        e c/m chemical-plant 2.5,4.5 N recipe=sulfur"""
    NETS = {"w": ([("w/pump", "water")], [("c/m", "water")])}

    def test_a_pipe_run_connects(self):
        rep = connect.connect(L(self.PUMP_TO_CHEM), CAT, self.NETS)
        r = rep.nets["w"]
        self.assertTrue(r.connected and r.fluid)
        self.assertEqual((r.segments, r.carriers, rep.checks), (1, 2, []))
        self.assertIn("fluid joins", rep.summary())

    def test_a_gap_is_unrouted(self):
        rep = connect.connect(L(self.PUMP_TO_CHEM.replace("e ~w/p1 pipe 1.5,2.5 net=w", "")), CAT,
                              self.NETS)
        self.assertEqual(rep.nets["w"].status, "unrouted")
        self.assertTrue(str(rep.checks[0]).startswith("UNROUTED    net w: 0 of 1"))

    def test_the_wrong_box_is_not_reached(self):
        # the pipe ends on the gas input (the right one): the water box is not reached, a LEAK
        rep = connect.connect(L("""
            e w/pump offshore-pump 3.5,0.5 N rate=1200
            e ~w/p0 pipe 3.5,1.5 net=w
            e ~w/p1 pipe 3.5,2.5 net=w
            e c/m chemical-plant 2.5,4.5 N recipe=sulfur"""), CAT, self.NETS)
        self.assertEqual(rep.nets["w"].status, "unrouted")
        self.assertEqual([str(c) for c in rep.checks if c.code == "LEAK"],
                         ["LEAK        net w: ~w/p1 joins c/m (its petroleum-gas box), which is not "
                          "an endpoint of w"])

    def test_two_nets_side_by_side_leak(self):
        rep = connect.connect(L("""
            e ~a/p0 pipe 0.5,0.5 net=a
            e ~b/p0 pipe 1.5,0.5 net=b"""), CAT)
        self.assertEqual([str(c) for c in rep.checks if c.code == "LEAK"],
                         ["LEAK        net a: ~a/p0 joins ~b/p0 (net b)"])

    def test_pipe_to_ground_pairs_as_measured(self):
        def pairs(text):
            return connect.graph(L(text), CAT).fluid_pairs
        self.assertEqual(pairs("""
            e a/g0 pipe-to-ground 0.5,0.5 W net=a
            e a/g1 pipe-to-ground 10.5,0.5 E net=a"""), {"a/g0": "a/g1", "a/g1": "a/g0"})
        self.assertEqual(pairs("""
            e a/g0 pipe-to-ground 0.5,0.5 W net=a
            e a/g1 pipe-to-ground 11.5,0.5 E net=a"""), {})            # 11 is too far
        self.assertEqual(pairs("""
            e a/g0 pipe-to-ground 0.5,0.5 W net=a
            e b/g0 pipe-to-ground 3.5,0.5 W net=b
            e a/g1 pipe-to-ground 6.5,0.5 E net=a"""), {"b/g0": "a/g1", "a/g1": "b/g0"})
        self.assertEqual(pairs("""
            e a/g0 pipe-to-ground 0.5,0.5 W net=a
            e b/g0 pipe-to-ground 3.5,0.5 N net=b
            e a/g1 pipe-to-ground 6.5,0.5 E net=a"""), {"a/g0": "a/g1", "a/g1": "a/g0"})

    def test_a_crossing_under_another_net(self):
        rep = connect.connect(L("""
            e ~a/p0 pipe 0.5,2.5 net=a
            e ~a/g0 pipe-to-ground 1.5,2.5 W net=a
            e ~b/p0 pipe 3.5,0.5 net=b
            e ~b/p1 pipe 3.5,1.5 net=b
            e ~b/p2 pipe 3.5,2.5 net=b
            e ~b/p3 pipe 3.5,3.5 net=b
            e ~b/p4 pipe 3.5,4.5 net=b
            e ~a/g1 pipe-to-ground 5.5,2.5 E net=a
            e ~a/p1 pipe 6.5,2.5 net=a
            e ~c/p0 pipe 1.5,1.5 net=c"""), CAT)
        self.assertEqual(rep.leaks, [])                 # c's pipe stands beside a's end: no join
        self.assertEqual(rep.graph.fluid_pairs["~a/g0"], "~a/g1")
        self.assertEqual((rep.nets["a"].segments, rep.nets["b"].segments), (1, 1))

    def test_a_boiler_passes_water_on_and_feeds_its_engine_directly(self):
        # boilers facing south: water on their north row, steam out of the south face
        lay = L("""
            e p/pump offshore-pump 0.5,0.5 W rate=1200
            e ~w/p0 pipe 1.5,0.5 net=w
            e b/b1 boiler 3.5,1 S fuel=coal
            e b/b2 boiler 6.5,1 S fuel=coal
            e e/e1 steam-engine 3.5,4.5 N role=engine
            e e/e2 steam-engine 6.5,4.5 N role=engine""")
        nets = {"w": ([("p/pump", "water")], [("b/b1", "water"), ("b/b2", "water")]),
                "s": ([("b/b1", "steam"), ("b/b2", "steam")], [("e/e1", "steam"), ("e/e2", "steam")])}
        rep = connect.connect(lay, CAT, nets)
        self.assertTrue(rep.nets["w"].connected)        # b2 through b1's water box
        self.assertEqual((rep.nets["s"].reached, rep.nets["s"].pairs), (2, 4))   # two halves
        self.assertEqual(rep.leaks, [])

    def test_machines_of_two_nets_joined_directly_leak(self):
        rep = connect.connect(L("""
            e b/b1 boiler 1.5,1 S fuel=coal
            e b/b2 boiler 4.5,1 S fuel=coal"""), CAT,
            {"w1": ([], [("b/b1", "water")]), "w2": ([], [("b/b2", "water")])})
        self.assertEqual([lk.text for lk in rep.leaks],
                         ["b/b1 joins b/b2 directly (its water box, net w2)"])

    def test_rorys_nuclear_plant_is_traced(self):
        rep = connect.connect(fkp.load(PLANT), CAT)       # captured from world 3, no netlist
        self.assertEqual({n: r.status for n, r in rep.nets.items() if "fluid" in n},
                         {"reactor/fluid0": "connected", "reactor/fluid1": "connected"})
        self.assertEqual(rep.nets["reactor/fluid1"].consumers,
                         ["reactor/steam-turbine0", "reactor/steam-turbine1"])
        self.assertEqual(rep.leaks, [])

    def test_an_unpaired_end_is_listed(self):
        rep = connect.connect(L(self.PUMP_TO_CHEM.replace("e ~w/p1 pipe 1.5,2.5 net=w",
                                                          "e ~w/g0 pipe-to-ground 1.5,2.5 N net=w")),
                              CAT, self.NETS)
        self.assertEqual(rep.nets["w"].unpaired, ["~w/g0"])


if __name__ == "__main__":
    unittest.main()
