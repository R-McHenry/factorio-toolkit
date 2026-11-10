# 54-presearch: what a rebuild of the T6 flower does before its first search

Branch `claude/54-presearch`, cut from main 04be9ae (3.2.7), 2026-11-10, on paper copies of the
compact T6 flower (`lab-session\fk-t6`: 6478 nets, 43,755 entities, 1284 sealed modules).
Copies: `lab-session\fk-t6q` (the committed state after the compact2 build: a no-op rebuild) and
`lab-session\fk-t6r`, `fk-t6s` (the same with the committed `.fkp` from before the compaction,
`flower_ground.fkp.before-compact2`: every module moved, as compact2 found it). Paper builds to
`--to route`, sampled every 5 s (`scratchpad\sampled.py`).

## What cost what

Two cases, both on 3.2.7 (04be9ae). Samples every 5 s; seconds are samples x 5.

- **No-op rebuild** (fk-t6q, nothing changed; the same cost as the 23-kind-line switch's 180 s
  route step in `fk-t6\game\boot1.out`): route 197 s. `seal_checks` 125 s (every entity's tiles
  for every one of the 1284 sealed modules), the design database 40 s (`read_all` 30,
  `_write_nets` 10), the rest under 5 s each. No search.
- **Moved-placement rebuild** (fk-t6r/s: the committed `.fkp` from before compact2, so every
  module stands somewhere new and the committed carriers stand where they were): 2819 committed
  routes are faulty ("would SPILL", "patching it failed") and each faulty net's `_patch_net` built
  `connect.graph` over the whole layout (43,755 entities + every port) to judge its patch: 2819
  whole-layout graphs before the first search. 3.2.6 spent 4603 s there (`fk-t6\game\compact2.out`);
  3.2.7 still does (old code on fk-t6r: over 1970 s in `_standing` / `_patch_net` and no search yet when this was written; see Numbers). 3.2.7's change did not touch it: the
  23-kind-line build was fast only because nothing moved.

After the change, the moved rebuild's 223 s route step: standing/patch 50 s, design database 80 s
(`_write_nets` 45, `read_all` 35), search 30 s, repair/judge 20 s, store keys 10 s; the first search
starts about 70 s in (it was 4,200-4,500 s on 3.2.6). These runs shared the CPU with other
builds, so seconds are high, not low.

## The changes (fkcore/route.py)

1. `_standing` / `_patch_net` / `_Patch`: a faulty net's patch judges on the graph of the ground
   around the net (`_Near`), not of the whole layout. The window is the 8-tile cells (`_Cells`)
   around the net's old carriers, its ends (machines and their port edges), every carrier of its
   member nets on the ground and the patch's own carriers, out to a margin past the farthest an
   edge reaches (`_reach_margin`: the longest underground / pipe-to-ground max_distance + 8, at
   least 16; a bounding box was tried first and was too big for the long nets): every edge at the net's
   carriers and ends, and the via of each, is then the whole graph's, which is all the judge reads
   (reach, serving, trunk, the leaks at its carriers, the unpaired undergrounds). One index by
   place of everything that is or was on the ground, and a `live` test (the routes still waiting
   for their patch, and what `new` holds now), so no ground list is built per net. A `_Near` with
   no window (no route, no ends) falls back to the whole ground. The search ground of a patch
   (`base`, `fronts`, `blocked`, `spans`, `clear`, and the ground list itself) is worked out on
   first use: a patch that ends before any search never walks the layout. The port edges given
   to each windowed graph are the ones with a tile in the window.
2. `_standing`'s judge: the first leak of each committed route from a key index of the report's
   leaks (was a scan of every leak per net).
3. `_ends_of`: `_placed`'s test without copying every port of the layout per call.
4. `seal_checks`: each sealed module judges the entities with a tile in its box, its own (key
   under it) and its nets' carriers, from one pass of indexes; was every entity's tiles for every
   module (1284 x 43,755). Same lines, same order.

Behaviour: the same nets kept, patched, held and routed again, the same carriers. Checked on the
flower (route.txt and every net file identical, old code vs new, from the same snapshot) and in
`tests/test_presearch.py` (a patched net and a moved chest with windowed graphs against whole
ones; seal_checks against the old whole walk, with FRAME and both crosses-frame lines).

## Numbers

Route step seconds (`out\timings.txt`), same snapshot, old code (54-base worktree, 04be9ae) vs new:

| case | 3.2.6 | 3.2.7 (old) | 54-presearch |
|---|---|---|---|
| no-op rebuild (fk-t6q) | - | 197.0 s | 51.6 s |
| moved placement (fk-t6r/s) | 4603 s (compact2) | over 1970 s, still patching (run going) | 222.6 s (first search ~70 s in) |

Routes: no-op, `route.txt` and every net file identical old vs new (timing lines aside). Moved:
the old-code run had not finished when this was committed; its route.txt is compared in a follow-up. Two new runs (bbox window, cell window) gave identical `route.txt`.

## Tests

- `tests/test_presearch.py` (new, 3 tests): OK.
- The merge set from v5\CLAUDE.md plus test_presearch and the patch tests: 650 tests, OK (29 skipped), 643 s.
- `tests.test_dnp` fails on 04be9ae as well (not this branch).

## Not done

- The design database's file I/O (`design.read_all` twice, `_write_nets`: 6478 net files) is
  about 20-40 s of a route step on the flower, now the biggest part of a no-op's.
