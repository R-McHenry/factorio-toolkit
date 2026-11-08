"""PLAN-LANES phase 1: the lane physics table (fkcore.lanephys) says what CORE-V2.md's "Lane
physics" rows say (measured on 2.0.77, docs/LAB-LANES-20261020.md). Directions: 0 N, 4 E, 8 S,
12 W; L and R looking along the flow. Every case below is a belt heading north (0).
"""
import unittest

from fkcore import lanephys as phys

N, E, S, W = 0, 4, 8, 12
A, B = frozenset({"A"}), frozenset({"B"})
AB = A | B


class LaneRows(unittest.TestCase):
    def test_every_rule_has_its_row(self):
        for via in phys.KEEP + ("side", "ug_side", "drop", "turn_drop", "mine", "pickup"):
            self.assertIn(via, phys.RULES)

    def test_straight_turn_tunnel_splitter_keep_lanes(self):
        """Row 1: straight belt, turn, underground pair, splitter: every item keeps its lane."""
        for via in phys.KEEP:
            edges, blocked = phys.moves(via)
            self.assertEqual({(a, b) for a, b, _r in edges}, {("L", "L"), ("R", "R")})
            self.assertIsNone(blocked)
            self.assertEqual(phys.carry(via, {"L": A, "R": B}), {"L": A, "R": B})

    def test_side_load_is_a_two_to_one_merge(self):
        """Row 2: a belt into the side of a belt: both incoming lanes onto the near lane."""
        # from the west (moving east): the belt's left side, so its left lane
        self.assertEqual(phys.carry("side", {"L": A, "R": B}, E, N), {"L": AB})
        # from the east (moving west): its right lane
        self.assertEqual(phys.carry("side", {"L": A, "R": B}, W, N), {"R": AB})
        # the lane entering further upstream (the south side, the source's right) goes first
        edges, blocked = phys.moves("side", E, N)
        self.assertEqual(edges, (("R", "L", 1), ("L", "L", 2)))
        self.assertIsNone(blocked)
        # in line is not a side-load: no lane reached
        self.assertEqual(phys.moves("side", N, N), ((), None))
        self.assertEqual(phys.moves("side", S, N), ((), None))

    def test_two_side_loads_make_a_pair(self):
        """The smelter stack's join: A from the left side, B from the right, nothing behind:
        A on the left lane, B on the right (pairs.py's construct, by the rule alone)."""
        held = {}
        for src, nets in ((E, A), (W, B)):
            for lane, got in phys.carry("side", {"L": nets, "R": nets}, src, N).items():
                held[lane] = held.get(lane, frozenset()) | got
        self.assertEqual(held, {"L": A, "R": B})

    def test_underground_side_load_drops_the_closed_lane(self):
        """Row 3: into the side of an underground end, only the open-side lane goes through."""
        # an entrance is open upstream (south): from the west, the source's right lane (south)
        edges, blocked = phys.moves("ug_side", E, N, "in")
        self.assertEqual(edges, (("R", "L", 1),))
        self.assertEqual(blocked, "L")
        self.assertEqual(phys.carry("ug_side", {"L": A, "R": B}, E, N, "in"), {"L": B})
        # an exit is open downstream (north): the source's left lane (north) goes through
        edges, blocked = phys.moves("ug_side", E, N, "out")
        self.assertEqual(edges, (("L", "L", 1),))
        self.assertEqual(blocked, "R")
        # so a pair's join on an underground entrance loses a net: what 2.1.31's no_bend forbids
        held = {}
        for src, nets in ((E, A), (W, B)):
            for lane, got in phys.carry("ug_side", {"L": nets, "R": nets}, src, N, "in").items():
                held[lane] = held.get(lane, frozenset()) | got
        self.assertEqual(held, {"L": A, "R": B})       # each net still lands, on one lane
        self.assertEqual(phys.carry("ug_side", {"L": A, "R": frozenset()}, E, N, "in"),
                         {"L": frozenset()})         # but a net on the closed lane is lost

    def test_inserter_drop(self):
        """Row 4: across a belt the far lane; in line always the right lane."""
        self.assertEqual(phys.drop_lane(W, N), "L")   # on the belt's right, dropping west
        self.assertEqual(phys.drop_lane(E, N), "R")   # on its left, dropping east
        self.assertEqual(phys.drop_lane(N, N), "R")   # in line, either way
        self.assertEqual(phys.drop_lane(S, N), "R")

    def test_turn_drop(self):
        """2.1.25: onto a turning belt, the inside lane from an outer side, the outside lane from
        an inner side (where the belt comes in or goes out)."""
        come, go = N, W                               # a left turn: inside is the left lane
        self.assertEqual(phys.turn_drop_lane(come, go, N), "L")
        self.assertEqual(phys.turn_drop_lane(come, go, E), "L")
        self.assertEqual(phys.turn_drop_lane(come, go, S), "R")
        self.assertEqual(phys.turn_drop_lane(come, go, W), "R")

    def test_drill_drop(self):
        """Row 6: a drill drops onto the near lane (in line: the right lane)."""
        self.assertEqual(phys.mine_lane(E, N), "L")    # a drill west of the belt, facing east
        self.assertEqual(phys.mine_lane(W, N), "R")
        self.assertEqual(phys.mine_lane(N, N), "R")

    def test_unknown_move(self):
        with self.assertRaises(ValueError):
            phys.moves("teleport", E, N)


if __name__ == "__main__":
    unittest.main()
