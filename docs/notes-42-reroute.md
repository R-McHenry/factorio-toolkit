# 42-reroute: why agents see "rerouting" on a rebuild (2026-11-09, 01:00-02:00)

Rory: "identify rerouting problems, and make it so that agents don't end up rerouting most times.
It should be relatively rare for a change to invalidate a route elsewhere." A second framing from
him mid-round: "a router cache that doesn't redo the same calculations with the same constraints".

Branch `claude/42-reroute`, cut from main `cfb10f0` (3.1.4). Measured on copies of the megabelt
designers' games (`lab-session\megabelt\work\<river>\game`, built on paper to the route step with
`flow.run(..., to="route")`; the scratch runner and its logs are session-local).

## What was measured

A **no-op rebuild** (the same source twice) on five designer bases, 3.1.4 as released:

| base | 2nd build summary | searched | note |
|---|---|---|---|
| ridge | 584 routed, 737 kept, 2 patched | 0 | the 584 are pass-through nets; 2 pairs patched, one lost 9 carriers |
| fen | 192 routed, 362 kept | 0 | 152 "laid from the store" (zero-carrier connection nets), 40 pass-through |
| core | 290 routed, 318 kept, 16 patched | 0 | 290 pass-through; 16 lane pairs patched "nothing new" every build |
| meadow | 85 routed, 118 kept | 0 | 85 pass-through, three builds identical |
| circuit (designer's own log) | 600 routed, 899 kept, 10 patched | 0 | 600 pass-through; 10 pairs patched "nothing new" |

So the router searches nothing on a no-op. **The key is clean too:** within one build, the five
`Split` instances of ridge differ only in `net p/items` (their `item=` parameter), FurnB's 284
cells fall into 3 keys (iron, steel, stone), Spring24's six instances into 2 (`z` is the stone
one). Nothing position-dependent leaks into a key (checked with the per-part shas below).

The re-routes in the designers' own logs follow **real source changes**: fen renamed `rx/cb/*` to
`rx/*` between builds (every net under it is a new name: nothing pinned, the sealed insides come
from the store, 417 of 475 laid from it; the 10 fluid nets "ends changed" were nets whose
consumers were not placed in the last layout); core moved or re-sized its yellow stack (41 cell
nets judged SPILL because their ends moved: the first failing check in `_standing`, then 39 laid
as twins). Legitimate, and the store made them cheap.

## What was wrong

1. **Standing lane pairs judged faulty every build** (`route._standing`): the idle-carrier check
   counted a lane pin's stub (`_is_stub`, one empty belt into the side of a join) as a carrier
   that serves no end, so every pair with a stub was "faulty", went to `_patch_net` (which keeps
   stubs), and came back "patched: nothing new; N of N carriers kept". Core 16 pairs a build,
   circuit 10, ridge 2, works 1. Each costs a connect graph and a patch; the paste then sees them
   as changed. Fixed: stubs are left out of `idle`, as `_patch_net` leaves them. Core's no-op:
   334 kept, 0 patched (was 318 + 16).
2. **The summary counted pass-through nets as routed.** "world: 584 routed, 737 kept" on a no-op
   is what an agent reads as "it re-routed everything"; the 584 are nets whose ports meet on one
   edge or drills dropping straight in, which lay nothing. `Routed.passthrough` (new) holds
   them, and the line reads `5 routed, 737 kept, 584 pass-through (...)`. Their per-net lines
   stay `routed X: ... nothing to lay`.
3. **A store miss said nothing about why.** `route.unit_key` is now `unit_parts` (named parts,
   the same sha: stored keys stay valid) plus `key_of_parts`, `part_shas` and `parts_differ`;
   an entry's `inputs.parts` holds a short sha per part (`router`, `width`, `height`, `kind`,
   `rot`, `children`, `settings`, `instances`, `standing`, `catalog`, `terrain`, and per net
   `net x/items`, `/starts`, `/goals`, `/taps`, `/sources`, `/reserved`, `/lanes`, `/skip`,
   `/fluid`, `/straight`, `/wide`, `/pin`, `/m2m`, `/parts`, `/seed`). A unit that misses the
   store while its module has a `current` entry with parts gets a line: `compiled  a: not in the
   store; Gears's last entry (3f3459bd) differs in instances, net g/sources`. Every build writes
   `out\design\<factory>\units.json` (unit -> module, key, from, nets, parts, differs), so a
   build-to-build diff of the keys is a file diff. `compiled.Store.inputs(module, key)` reads
   an entry's inputs; `route._store_differs` makes the comparison.

4. **Stacked fluid cells put their column through the store and the fluid judge every build.**
   A fluid net between two ports that meet on one edge (a Stack's cells: `c/heavy_in_3`) lays
   nothing, but it was no pass-through: with no carriers it was never pinned, so each build it
   was "laid this run", its column went through the store (`_fits`, then `Pass.judge` for each
   such net), and each judge built a connect graph with every fluid port of the layout in it
   (fen: 592 ports). Fen's no-op route step: 76 s with nothing searched, 60 of them in
   `connect._port_joints` under the judge (`tools/buildbench.py --from route`). Fixed twice over:
   `fluid_route._abut` nets join `abut` in `_route_layout` (pass-through, like two belt ports),
   and `fluid_route._judge` hands the connect graph only the port edges within two tiles of the
   ground it judges (`_edges_near`). Fen's no-op: 21 s, `1 routed, 362 kept, 191 pass-through`
   (the one routed is `rx/f5_gas3`, a direct join of two boxes with nothing to lay, below). The
   columns that hold such cells key anew once (their `nets` no longer list the pass-throughs:
   fen stored 9 entries on the first build after, none on the next); no ROUTER bump, the old
   entries are simply never matched again.

## Rory's "router cache" framing

The compile store already is that cache for everything inside a sealed module: its key is the
exact set of inputs the unit's search sees (frame, what stands, ends, lanes, children, settings),
and a hit lays the routes without a search. What it does not cover is the nets outside every
sealed module (the world's trunks), whose "cache" is the pin-and-patch judge (`--only stale`):
keep what still connects, patch the rest. A per-net cache keyed on the ground in the net's search
box would rarely hit for those: a trunk's box is most of the plot, and almost any edit changes it.
The false re-routes found this round were all in the judge, not in the key, so the judge is where
the remaining work is (below). Nothing needs a ROUTER bump.

## Still open

- **A pair laid this build may carry a tail the judge trims next build** (ridge: `rx/steelE|rx/bka`
  lost 9 of 298 carriers on the first rebuild, "no end of the net needs them now", then stood).
  `_serving_only` trims a wide or pinned net's tail at lay time but not a lane pair's. Once.
- **Zero-carrier connection nets are "laid from the store" every build** (fen: 151 `c/a_in_N`
  style nets): nothing is searched, but the summary's "laid from the compiled store" count is
  mostly them. Harmless; a pass-through rule for them would quiet it.
- **A fluid net that is a direct join of two boxes** (fen's `rx/f5_gas3`: `0 pipes, 1 direct
  join`) lays nothing, so nothing pins it, and each build routes it again (one cheap search).
  The fluid analogue of a belt job's `direct`; a pass-through rule for it would make fen's
  no-op read `0 routed`.
- **Fen's no-op route step still takes 21 s with nothing searched** (ridge 28 s, core 13 s):
  the standing judge (`_standing`: one connect graph of the layout, a reach per end) and the
  fluid world's setup, not routing.
- **The designers build on paper (`fk build --to report_checks`)**, so `world.fkp` is the
  kickoff's and every build's "kept" rests on the design database alone (`_with_last_routes`).
  That held in every no-op here; it is worth knowing when reading "0 pinned from the committed
  .fkp" in their logs.
- A renamed block re-routes every net under it (new names). Not a bug; a doc line.

## Tests

`tests/test_compiled.py::test_a_store_miss_says_which_part_of_the_key_changed` (the parts, the
line, units.json, a no-op says nothing). The existing compiled, flow, design, merge, size,
friction_2062, stacks and fluid_ports modules cover the summary line and the stub rule.
