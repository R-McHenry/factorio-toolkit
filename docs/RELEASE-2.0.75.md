# Toolkit 2.0.75: overlapping modules are a warning

Rory, 2026-10-30: "two overlapping module plots should just be a warning, rather then a blocking
error. Then when it routes, the other stuff in the way still counts as an obstacle again".

## What was wrong

Two sealed modules whose frames overlapped could not use the tiles they shared. A net inside a
sealed module routes in its own frame with every other frame blocked, so the shared tiles were
blocked for both: each saw them as the other's frame. A route that needed them failed
(`no free tile is reached from every driver and consumer`), and a belt laid there by hand was a
`crosses-frame` line.

## Now

- **`overlap`** (a warning, at `place`): two sealed modules' frames share tiles, neither inside the
  other. The line gives the shared box, and names any port of either that opens inside the other's
  frame (a net from outside both can't reach it).
- **The shared tiles are both modules' ground.** A net inside either module may route on them; the
  rest of the other module's frame, and every template frame in it, stays blocked. What the other
  module has laid there (its machines, and routes laid before) is in the way as entities. Nets
  are laid one at a time as before, each seeing the ones before it, and a net that fails goes to
  the front of the next pass.
- The fluid router (`fluid_route.net_frames`) shares the tiles the same way.
- `crosses-frame` no longer reports a module's own carrier on tiles its frame shares with another.
- Unchanged: two entities on one tile are `malformed` and stop the build; nets outside both
  modules keep off both frames; plots (several in one surface) still may not overlap.

## Tests

`tests/test_module_overlap.py`: the shared box; the warning; both modules routing with one of
them through the shared columns, with no `crosses-frame` and no invariant; the other module's
entity in the way; a tile collision still stopping; a port inside the other frame named; a
sealed child inside its parent is no overlap.
