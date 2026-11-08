# 31-store: one compile store (PLAN-3.1, wave 1)

Branch `claude/31-store`, cut from main `fa99ec8` (3.0.3). Closes REVIEW-3.0 "The two compile-once
stores: they coexist, and that is a cost": 3.0 had the design store (`fk compile`,
`out\design\modules\<module>\<key>.fkp`, `compiled.ROUTER`) and the router store
(`out\compiled\<key>.json`, `route.COMPILE_VERSION`). 3.1 has one.

## The store

`fkcore/compiled.py` (the layout is documented at the top of the module):

```
out\compiled\<module>\<key>.json     one entry per key, never rewritten
out\compiled\<module>\current        the key the last build wrote or laid from
```

An entry: `router` (the ROUTER it was laid by), `module`, `key`, `unit` (the instance it was first
laid from), `inputs` (frame size, the nets it holds, the children's keys, which nets were seeded,
the router's settings: for the reader) and `nets`: the carriers of each of the unit's own nets, in
the unit's unturned frame (top-left 0,0), the router store's form (a unit turned 180 degrees stores
unturned, `route._UnitTurn`; a lane pair's inserter keeps its `a+b`).

The base is the router store, as the review recommended: it handles nested units (every sealed
module is a compile unit, innermost first), 180-degree twins and twins within one build. The
design store's pieces moved onto it: `fk compile`, `--reuse-lab`, the research check
(`avail.locked`: an entry holding an entity the force can't build is not taken), and the
per-module folder with a `current` pointer.

## The key: one rule

`route.unit_key` (was `_compile_key`), a sha over everything the unit's own nets are laid to,
relative to its frame:

- `compiled.ROUTER` (`"3.1"`), the one router version. `route.COMPILE_VERSION` is gone. Raise
  ROUTER when a router change would lay the same inside otherwise; every entry is laid again once.
- The module's source and parameters, through what they elaborate to: the frame's size, the
  instances placed in it (kind, parameters, place, turn), every entity standing in the frame
  (machines, Literals, the children's routes, a held route), and each net's ends, items, lanes,
  taps and flags.
- Its children's keys: the sealed units inside it, keyed first (new, explicit; the children's
  routes were already in the key as what stands).
- The catalog and terrain facts: the catalog's version and the footprint of every entity name
  standing in the frame; the terrain tiles in the frame; the router's settings (the hand, the
  ribbon tiers, the pipe material, m2m), which were not in the 3.0 key.
- The player's route-file inputs (3.0's per-net files, `fkcore.design`): a held net stands in
  the frame and keys as what stands; a seed (`fk seed`) is in the key as the net's seed (new; a
  seeded net could be laid from the store without its seed before).

A twin (the same key) is laid from the first one's routes, moved to its frame, if they fit
(`_fits`); if not, it is routed on its own, as before.

## What uses it

| | reads | writes |
|---|---|---|
| the route step (`route`, any `--only`) | the game's `out\compiled` (+ lab stores with `--reuse-lab`) | the game's `out\compiled` |
| `fk compile MODULE` | same | same; the router does the twin / already-compiled logic |
| `fk lab NAME` (and `--keep`, `measure`) | the game folder's `out\compiled` (`lab.compiled_store`, unchanged path) | same |
| `fk status GAME` | lists modules, entries, current keys, old material | - |
| `route --store DIR` | DIR | DIR |
| `route --store none`, `route --compiled no` | nothing | nothing |

`fk compile MODULE` routes every placed instance of MODULE (their nets and their children's) with
every other net skipped, through the same `route_layout(..., store=Store)`; its lines come from
`Routed.compiled` ("routed and stored", "the same inside as a", "already compiled").

`Routed.compiled` (new): sealed unit -> {module, key, nets, from ("routed" | "twin X" | "store" |
None), stored, refused}. The route step's lines: `compiled  b: 2 nets laid from the store (Gears
<key>)`, `compiled  stored a (out/compiled)`, `compiled  b: its stored entry (Gears) holds
fast-inserter, not researched here: routed again`, and the summary `N routed, M kept (P pinned
from the committed .fkp, K laid from the compiled store)`.

Nets laid from the store count as `routed` (they are laid this build, nothing searched), as a
twin's do; the 3.0 design store counted them as `kept`. Their design-db net files say `routed`.

## Old stores

Not read, not migrated (Rory: old material is reference). A build whose `out` holds entries of
either old format (`out\compiled\*.json` flat; `out\design\modules\*\*.fkp`) says so in one line:
`compiled  old entries not read, reference only: 54 of the 2.1 router store (out/compiled/*.json)
...; the 3.1 store is out/compiled/<module>/<key>.json (router 3.1)`. `fk status` repeats it.
The lab's `out\compiled` held 54 of the 2.1 format on 11-08; they are laid again once.

## Tests

`tests/test_compile_once.py` (11, router level: twins, turned twins, nested, another ROUTER, two
builds of an unchanged module reuse the entry, an old store is said once and not read, the
store's lane-pair form) and `tests/test_compiled.py` (9, flow level: insides route once and a move
lays from the store, the key is the inside not the place, a seed is in the key, a hand-edited
route file changes the key and is read, `fk compile` then the world build, `fk status`,
`--reuse-lab`, an entry the force can't build is routed again, `--compiled no` / `--store none`,
an old design store is said once). Run with `test_route_units`, `test_lab_megabase`, `test_route`:
all pass (34 + 20).

### The hand-edited route file

PLAN-BUILD §2: "a hand-edited route.fkp is an input like any other". In 3.1 the route files are
still 3.0's per-net files, `out\design\<factory>\nets\<net>.net`, and the way the player makes an
edit an input is 3.0's: `status: held` (or `fk hold`; a seed through `fk seed`). The test cuts a
belt from `a/g`'s file, holds it, and asks `a/fe` again: the module keys with the cut route
standing (a new entry, `inputs.nets == ["fe"]`), the paste has the file's carriers, a repeat
build lays `a/fe` from the new entry, and lifting the hold brings the first key back.

An unmarked edit (the file left `routed`) is read only by 3.0's rule (`_with_last_routes`: when the
last build stopped before `write_layout`); otherwise the committed `.fkp` wins. Making every edit
an input without a status needs a "written by the step" stamp to tell an edit from the step's own
write; left for the placements wave, where route files become per-module artifacts.

## What changed for the agent (TOOLKIT.md lines that are now wrong; the docs wave rewrites them)

- ~190: "Every module routed whole is kept in `game\out\compiled\`" is right again, but the
  files are `out\compiled\<module>\<key>.json`, not `out\compiled\<key>.json`; "(your `fk lab`
  builds write there too)" still holds.
- ~495-505 "Compiled modules": `out\design\modules\MODULE\` is gone; the store is
  `out\compiled\MODULE\`. "keyed by what is inside (its machines, inner nets and ports, the turn,
  the router version)" is now the fuller key above (children's keys, catalog and terrain facts,
  the router's settings, seeds and held routes). "the route step says `compiled  P: k inner nets
  from its stored inside`" is now `compiled  P: k nets laid from the store (MODULE key)`.
  "`--with "route --reuse-lab"` makes even a `fk route` of named nets lay the stored insides":
  every route step reads the store now; `--reuse-lab` only adds the lab builds' own stores (a
  lab built from the game folder writes the game's store, so it is rarely needed).
- The two descriptions of two caches become one section; "an agent that sees a stale module has
  to know to clear both" is no longer true: delete `out\compiled\MODULE` or raise nothing: a
  changed inside changes the key by itself.
- `fk status GAME` now ends with the store's lines.
- RELEASE-3.0.md / RELEASE-3.0.1.md describe the two stores as history; nothing to change there.

## For the integrator

- `fkcore/flow.py`: edits are confined to `s_route` (the store construction, ~1053-1063; the
  removed design-store read block, ~1123-1141; the summary line and the `_compiled_lines` call,
  ~1196-1210) and to `_route_compile`, `_compiled_lines` (new), `_compiled_dirs`;
  `_store_compiled` is deleted. The `from . import compiled as compiledmod` import and
  `Ctx.compiled` stay. Nothing else in flow.py changed, so a merge with 31-surface or 31-world
  should be clean unless they touch `s_route`'s store lines.
- `fkcore/__main__.py`: two help strings and two lines in `_design` (`fk status` prints
  `compiled.status_lines(out)`).
- `fkcore/route.py`: `COMPILE_VERSION` removed; `_compile_key` -> `unit_key` with three new
  arguments; `_store_save` / `_store_load` take a `Store` and a module name; `_module_of` new;
  `Routed.compiled` new; the `store` argument of `route_layout` takes a path (wrapped) or a
  `compiled.Store`.
- `fkcore/lab.py` unchanged (`compiled_store(game)` is the right path already).
- The release note for 3.1 should carry: one store, ROUTER 3.1, every stored module laid again
  once, old stores reference only.

## Open

- An unmarked hand edit of a route file as an input (above): needs the step's own write stamp.
- `fk compile` reports per instance; a nested child compiled under its parent gets its own entry
  but no line (the parent's line covers it).
- Pruning: entries are never deleted. PLAN-BUILD §2 keeps the last few per module and any a
  placement refers to; that is the placements wave's.
