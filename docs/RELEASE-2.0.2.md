# Toolkit 2.0.2 (2026-10-22): a belt two nets share is patched, not laid again

No new rules: checks warn, never gate.

## Route patching for lane pairs

2.0 patches a net's committed route when an end is added or dropped (Rory, 2026-10-21: "Pin
what stands and make patch changes rather than regenerating the base"), but a lane pair
(`lanes ore_ | fuel`, one belt of two nets) was routed again whole: the patch worked on one net,
and a pair's job (`ore_|fuel`) has no ends of its own. Now a pair is patched by its two nets
(`route._patch_net`, `_Patch`): each net's drivers, consumers and reach are its own, and a new
carrier's `net=` says which lanes it carries.

- **A new consumer of both nets** branches off the belt of both lanes where every standing
  driver of each net reaches it: a splitter in place of a straight belt, or the belt's end run
  on. Both keep every item on its lane; the branch is `net=ore_|fuel`, a tap inserter
  `ore_+fuel`.
- **A new driver of one net** joins where it reaches every consumer of that net: onto the net's
  own belt (either side, or the back of a belt nothing feeds), or onto the pair's belt from its
  own lane's side only, since a side-load lands on the near lane (CORE-V2, "Lane physics"). An
  inserter from a new driver machine drops only onto the net's own belt (an inserter drops on the
  far lane). The new carriers are the net's own part of the pair (`~ore_|fuel/lb3`, `net=ore_`).
- **A dropped consumer** takes its branch up, as for one net.
- **The judge** reads each net of the pair: every pair of ends joined, no LEAK, every tunnel
  paired. When no branch fits, the pair is routed again whole, and `out\route.txt` says why.

Numbers, on the test smelter (ore and coal on one belt into a smelter row, 29 carriers): a second
smelter row on the pair keeps 28 of them (one straight belt of both lanes became the splitter) and
lays a 17-belt branch of both lanes; a second iron miner keeps all 29 and side-loads onto the
left lane; a second coal miner keeps all 29 and side-loads onto coal's own belt. Every net
connected, no LEAK, no `LANE` line. An unchanged rebuild of every game in `games\` keeps every
route. Tests: `tests\test_lanes_pairs.py` `PatchPairTest` (a consumer of both, a driver of each
net, a dropped consumer, the fallback).

692 tests OK.
