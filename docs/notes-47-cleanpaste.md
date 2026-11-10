# 47-cleanpaste: a paste on a free surface lands clean and comes back clean

Branch `claude/47-cleanpaste`, cut from main b3e9a14 (3.2.1), 2026-11-09 early afternoon. Rory,
watching the T6 flower on the lab: "I saw a lot of little paste-related issues: make sure you
can clear out an area consistently and have the base paste in cleanly."

## What the flower's pastes showed

1. **The toolkit's own stale entities stayed.** When the core's lab columns were re-routed, the
   old blue|purple belts stood on beside the new ones, and the diff said `marked ... kept in
   the plot until its owner decides by Rory_618`. `fkcore.own` is the mechanism for exactly this
   (the record of what the applies pasted; a dropped row is `unowned` and the next apply takes it
   up), but `apply`'s free path (`free=True`: the lab) never set `rep.own`, so the flow never
   saved the record and `out\own\lab.json` stayed the seed written at `write_layout`, with no
   rows. The old belts were then judged by the plots policy (`keep`), as a hand build of the
   last user's.
2. **A stand-in the design cannot say.** The T6 stands' sources were `Chest<requester>`; the lab
   has no logistic network, so no ore flowed until a Lua swapped the 26 chests for infinity
   chests, and every apply after that put a requester ghost back on each (the design said
   requester) and the diff listed them `ghost SHORT`.
3. **No way to empty ground before a surface-level paste.** `fk alone` empties its slot before
   every build (`alone.lua_clear`), but a design placed by a surface file (the flower) had
   nothing: what stood there from an earlier paste, or a hand build, met the paste.
4. Not the toolkit's: this session's Git Bash handed `FK_SCRIPT_OUTPUT` over with one backslash
   of the UNC path eaten, so the apply read beside the game's answer file (46-pairbox's
   `read_output` wait was found that way; `bin\fk.py` sets the env in Python and is fine).

## The changes

- `fkcore/apply.py`: on a free surface the toolkit's own entities the design dropped (in the
  apply's scope) are destroyed where they stand (`_destroy`, `link.lua_destroy_list`: the entity
  of that name on that position, or a ghost of it), a note says how many, and `rep.own` is the
  updated record, which the flow saves as it does for a play surface.
- `Chest<infinity, item=, rate=>` (`templates.py`, `expand.py`): an infinity chest holding its
  items at `INFINITY_COUNT` (1000, `mode exactly`, unfiltered items removed), a source for the
  model like a requester. The design says the stand-in, so the paste lays it and the diff knows
  it. LANGUAGE's Chest row says where it belongs (the lab).
- `fk clear GAME AREA [--surface S]` (`__main__._clear`): `alone.lua_clear` over an area of a
  free surface (everything but characters and resources), refused where the surface file does
  not say `free`. TOOLKIT chapter 13 names it with the other lab tools.
- `tests/data/flower/ground_flower.py`: the `Stand`'s source is the infinity chest.
- `tests/test_cleanpaste.py`: the chest's settings in the .fkp and the blueprint; a free apply
  with a dropped row in the record destroys it and returns the record; the Lua names each thing.

## Measured (the fk-t6 flower on the lab, this branch pinned)

- The stands' source changed to `Chest<infinity>`: the 26 `Stand` units keyed anew (`not in
  the store; Stand's last entry differs in ...`), the route step 288 s, `26 routed, 3348 kept,
  0 failed`; the apply placed 758 ghosts, 706 revived, 56 not: the design's infinity chests and
  new belts met the Lua-placed chests and the old stand belts that no record held (the record
  was still the seed, so nothing counted as dropped), and `out\own\lab.json` went from 0 to
  48,942 rows.
- `fk clear` on the 29 stand-in frames (88 entities each) and one more apply: 1727 ghosts
  placed and revived, 2 not (Rory's hand-placed pump and pipes), `diff ... ok 48940` of 48942,
  no Lua swap. The 126 `marked` left are old carriers outside the frames (the flower-level feeds'
  earlier routes) and Rory's own; the policy keeps them until their owner decides.
- From here a re-routed net's old carriers are in the record and go on the next apply: the core's
  lab field redesigned (one paired red|green port a column) and fen's water pump added, the apply
  said `free: 258 of the toolkit's own that the design dropped destroyed where they stood (261 in
  the record)`.
- The clean sequence, end to end: `fk clear . 2100,-600,3100,600 --surface lab` (49,116
  entities destroyed, resources and characters kept) then `fk build --from apply`: 48,826 ghosts
  placed and revived, 0 not revivable, `diff ... ok 48826`, nothing marked, nothing unowned.

## Module ghosts (evening)

Rory: "the pasting is not completely worked out, it still leaves ghosts for the modules". The
revive builds each machine, but its `modules=` stand as an item-request proxy (the blueprint's
insert plan) that robots would answer; none come on a free surface. On the standing flower:
`proxies=3127`. `link.lua_fulfil` puts each plan's stacks into the target's inventories and
destroys the proxy; run once on the lab by hand it answered `3127 6964 28` (proxies, modules
placed, stacks refused), then `proxies=0`. The 28 refused were productivity modules on recipes the
game takes no productivity on (rail, electric-furnace and the like in the mall rows); the template
now leaves them out with a `module-refused` check, so the model stops counting their bonus.
