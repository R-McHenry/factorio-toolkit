# Toolkit 2.0.45: a net is routed in its own neighbourhood first

Rory, 2026-10-26: "we should be routing a lot of independent small connections so done one at a
time ideally it would be just as fast as what we typically have."

## Why

A world plot holds the whole base, with its sub-factories as sealed modules inside it, so its frame
is a couple of hundred tiles across. Routing time grew with that frame's area, not with the length
of the connections. The four-rib bus plus independent chest -> assembler -> chest cells:

| design | frame | nets | before | now |
|---|---|---|---|---|
| the four-rib bus | 80x25 | 17 | 0.05 s | 0.05 s |
| + 8 cells beside it | 105x68 | 33 | 0.89 s | 0.22 s |
| + 8 cells 200 tiles away | 265x178 | 33 | 6.88 s | 0.24 s |
| + 16 cells, map-sized | 245x218 | 49 | 15.35 s | 0.48 s |

The profile (the 265x178 case): 13.0 of 13.7 s in the hub search. For a net that runs machine to
machine, `_hubs` ranks every free tile of the box by belt distance from each end (`_walk`, a flood
over the whole frame), so every short net paid for the whole frame.

## The change

`route._route_one` searches a net first in **its own box**: the bounding box of its ends and the
machines it inserts into or picks from, plus 12 tiles and a quarter of its extent, inside the frame
(`_near_box`, `_NEAR = 12`). A lane pair's parts count together. When nothing routes there, the net
is searched in the whole frame as before, so the bound never loses a route the frame allowed; it
only costs one more search for a net that has to go round something big.

Sealed modules already bound their own nets by their frames (2.0.36); this bounds the nets of the
level they sit in, which is where a world plot's long-haul and independent nets live.

## Verified

- `tests/test_near_box.py` (3): the box is the ends plus the margin, clipped to the frame; a short
  net 200 tiles from the rest is laid within its own box; a net walled off near its ends (a terrain
  wall 10 tiles thick, open only 60 tiles south) falls back to the frame and goes round.
- The full suite: **980 tests, OK** (977 before, plus 3). No existing route changed: every test
  that pins a route's tiles passes as it did.
