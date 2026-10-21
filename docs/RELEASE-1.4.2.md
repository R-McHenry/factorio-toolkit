# Toolkit 1.4.2 (2026-10-21, overnight): fixes from the players' FRICTION.md

Small fixes for what the two overnight players reported (the 2005 run's and the lead world's
FRICTION.md). No new rules: checks warn, never gate.

## Fixed

- **No edit is lost to a background fk** (`agent/fk.py`). The 2005 player's edits to base.fk and
  core.fk were silently undone: a background loop of its own ran `fk look` every 10 s, whose
  pull put the host's copy back over the fresh edit, and the stamp it wrote then made the next
  push skip the file (older mtime). The sync now goes by content: `out\.synced` keeps each file's
  hash at the last sync, a push sends what changed since, a pull keeps a file edited here since
  (the next push sends it), and two fk commands' syncs take turns (a lock). The first push after
  an older fk's plain stamp goes by mtime once.
- **The world line names ghosts no robot will build** (`kickoff/claude_loop.py`). The watcher
  reads which ghosts stand outside every powered roboport's construction area and says so:
  `UNREACHED: 32 of them stand outside every powered roboport's construction area, so no robot
  will build them (first: medium-electric-pole at 85,101)`, again every 10 minutes while it
  lasts. The 2005 player's grid split (a re-laid pole chain whose new poles stood out of every
  powered roboport's reach) was a silent deadlock, and at 02:10 it had 32 such ghosts east of
  its last roboport.
- **OFF_WATER** (`fkcore/flow.py`, floorplan): an offshore pump whose water tiles are dry ground.
  The lead world's kickoff plant stood where world 3 had a lake: no water, no power, and every
  look said OK.
- **A Literal reads a bare entity list** (`fkcore/literal.py`): `[{"name", "x", "y",
  "direction"}]`, as well as `{"entities": [...]}`, a blueprint string or `{"bp": ...}`; any other
  JSON says which shapes it takes (it said "a blueprint string starts with a version digit").
  LANGUAGE.md says it too, and that a lone roboport Literal needs its own pole.
- **`trash` on a requester** (`Chest<requester, item=stone, trash>`): the game's "trash
  unrequested", so what it no longer asks for goes back to the network (the 2005 player's stone
  requester kept 101 copper plates from its old list; it set the flag by Lua).

## Not in this release (reported, for the next round)

- A provider chest that still holds the old product after a one-off crafter's recipe changed.
- `cover robots` moving a standing roboport when a net changed (roboports locked, none spare).
- `cover power` re-laying poles so a part of the base loses its grid (the world line now shows
  the result; keeping standing poles that still serve is the fix).
- Logistic or circuit conditions on an inserter in the .fk language (per-item limits on a mall's
  output).
- A warning before the last of a non-renewable item goes (the lead world spent its kit's iron
  before any drill).
