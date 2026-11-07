"""2.1.32: signals planned from a network's rails (Rory, 11-07: "intersections need to be all chain
signals and rail signals only at the exit on the long segment")."""
import unittest

from fkcore import railsignals as rs


def line(x0, x1, y=1):
    """Eastward straight rails from x0 to x1 (positions at odd x, joints at even)."""
    return [("straight-rail", x, y, 4) for x in range(x0, x1, 2)]


class PlanTest(unittest.TestCase):
    def setUp(self):
        # a lane running east, a curve leaving it at x 50 (curved-rail-a facing 4 at 52,1 has an
        # end at 50,1 facing west), the lane long after the fork; a stop says which way it runs
        self.pieces = line(1, 50) + [("curved-rail-a", 52, 1, 4)] + line(51, 160)
        self.stops = [(21, 3, 4)]                 # facing east, 2 south of the lane (its right)

    def test_the_travel_spreads_from_a_stop(self):
        net = rs.Network(self.pieces, self.stops)
        self.assertEqual(sum(1 for e in net.exit if e is None), 0)
        self.assertEqual(net.conflicts, [])
        fork = (50, 1, 4)
        ins, outs = net.flow(fork)
        self.assertEqual((len(ins), len(outs)), (1, 2))
        self.assertTrue(net.is_junction(fork))

    def test_a_chain_signal_into_the_junction_a_rail_signal_out_onto_the_long_lane(self):
        sigs, notes = rs.plan(self.pieces, self.stops, long=42)
        chains = [s for s in sigs if s["name"] == "rail-chain-signal"]
        rails = [s for s in sigs if s["name"] == "rail-signal"]
        self.assertEqual(len(chains), 1)
        self.assertEqual((chains[0]["x"], chains[0]["y"]), (49.5, 2.5))   # right of eastbound
        self.assertEqual(chains[0]["d"], 12)                               # pointing against it
        self.assertEqual(len(rails), 1)
        self.assertGreater(rails[0]["x"], 50)          # after the fork, on the lane east of it
        self.assertLess(rails[0]["x"], 70)
        self.assertIn("1 chain signals, 1 rail signals", notes[-1])

    def test_a_short_segment_gets_a_chain_signal_out(self):
        sigs, _notes = rs.plan(line(1, 50) + [("curved-rail-a", 52, 1, 4)] + line(51, 70),
                               self.stops, long=42)
        self.assertEqual([s["name"] for s in sigs], ["rail-chain-signal"] * 2)
        # 11-07 (Rory): the exit stands past the curve's tiles, not 2 tiles after the fork
        self.assertGreater(max(s["x"] for s in sigs), 55)

    def test_a_merge_is_signalled_on_each_branch_before_the_rails_overlap(self):
        # 11-07 (Rory: "chain signals that are too close to the merging part of two rails"): a
        # diagonal feed merging into the lane at x 50 through two curves
        feed = [("straight-rail", 40 - 2 * k, 6 + 2 * k, 2) for k in range(8)] +             [("curved-rail-b", 43, 3, 12), ("curved-rail-a", 48, 1, 12)]
        sigs, notes = rs.plan(line(1, 50) + feed + line(51, 160), self.stops, long=42)
        chains = sorted((s["x"], s["y"]) for s in sigs if s["name"] == "rail-chain-signal")
        rails = [(s["x"], s["y"]) for s in sigs if s["name"] == "rail-signal"]
        self.assertEqual(len(chains), 2)                 # one on each branch
        lane = [c for c in chains if c[1] == 2.5][0]
        self.assertLess(lane[0], 43)                     # before the feed's tiles reach the lane
        feedc = [c for c in chains if c[1] != 2.5][0]
        self.assertLess(feedc[0], 43)                    # before the feed's curves
        self.assertEqual(len(rails), 1)                  # the exit, past the merge joint
        self.assertGreater(rails[0][0], 50)
        self.assertNotIn("left out", notes[-1])

    def test_unreached_pieces_are_said(self):
        _sigs, notes = rs.plan(self.pieces + [("straight-rail", 501, 501, 0)], self.stops)
        self.assertIn("1 of", notes[0])

    def test_a_segment_two_trains_fit_gets_a_chain_signal_half_way(self):
        # 11-07 (Rory: "a chain signal in the middle of a segment so that two trains can occupy
        # it"): a fork at x 50, 120 tiles of lane, a feed merging in at x 170
        feed = [("straight-rail", 160 - 2 * k, 6 + 2 * k, 2) for k in range(8)] +             [("curved-rail-b", 163, 3, 12), ("curved-rail-a", 168, 1, 12)]
        pieces = line(1, 50) + [("curved-rail-a", 52, 1, 4)] + line(51, 300) + feed
        sigs, notes = rs.plan(pieces, self.stops, long=42)
        lane = sorted((s["x"], s["name"]) for s in sigs if s["y"] == 2.5)
        exit_x = next(x for x, n in lane if n == "rail-signal")
        entrance = max(x for x, n in lane if x < 170)
        mids = [x for x, n in lane if exit_x < x < entrance]
        self.assertEqual(len(mids), 1, lane)
        self.assertGreaterEqual(mids[0] - exit_x, 42)          # a train's room on each side
        self.assertGreaterEqual(entrance - mids[0], 42)
        self.assertIn("half way", notes[-1])
        # a lane that runs out at a dead end gets none
        sigs, notes = rs.plan(line(1, 50) + [("curved-rail-a", 52, 1, 4)] + line(51, 300),
                              self.stops, long=42)
        self.assertNotIn("half way", notes[-1])


if __name__ == "__main__":
    unittest.main()
