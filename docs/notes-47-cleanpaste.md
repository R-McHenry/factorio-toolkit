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

## Measured

(the fk-t6 flower, after the merge: the stands re-pasted as infinity chests, no Lua swap, and a
re-route of a net leaving no old carriers behind)
