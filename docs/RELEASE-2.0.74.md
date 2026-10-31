# Toolkit 2.0.74: a patch keeps what stands (the 10-30 run's MIL step)

From `C:\fk-player\runs\20261030-1602-opus\FRICTION.md`: "`fk build` adding 2 consumers (a steel
row, a module 60 tiles east) to the main iron/coal/copper nets re-laid all three nets ("routed
again", ~620 belts) instead of patching, and pasted with 549 belts SHORT: robots tore the old
mains up before the new ones could be built, which stopped the base."

Since 2.0 a rebuild patches a standing net: a new end gets a branch off what stands. A net was
laid again whole when an end of it moved, when the new layout took one of its tiles, or when the
patch failed. Replayed offline from the run's files, the MIL step's patch failed for a bug, and
the other two triggers re-laid nets that a patch handles.

## Why the MIL step re-laid the mains

A new sealed module's ports were never patched in. A port end's role (`mil.so_in!`) was matched
against its module's machines, which don't hold the port (`mil/so_in`), so the patch laid no
branch to it. Its judge then found the port apart from the drivers, and the net was laid again.
Every main a new module plugs into went that way. `route._role_keys` gives a port role its port.

Replay: the run's `world-before-mil.fk` built fresh as the committed layout, then
`world-mil.fk` on it (the live pre-MIL .fkp is gone; this is the closest rebuild of it):

| net | before | after |
|---|---|---|
| fe_pl | routed again | patched: 2 splitters, 211 of 213 carriers kept |
| coal4 | routed again | patched: 2 splitters, 154 of 156 kept |
| cu_pl4 | routed again | patched: 1 splitter, 102 of 103 kept |
| st_out | routed again | patched: its end run on, 4 of 4 kept |

## A failed patch no longer re-lays a belt net

When no branch reaches a new end, a net with belts is held: its standing route stays as it is,
the net fails with `its standing route is kept as it is (N of M carriers), the new end is not
joined: ...; to lay the net again whole: fk build --reroute NET`, and the `no-route` check (in
every run's `stop_on`) holds the paste. Nothing that stands is taken up. A net of inserters
alone (direct insertion) is still laid again: nothing to tear up.

## Patches inside a sealed module

The patch searched with every module frame blocked, the net's own module included, so a net
inside a sealed module could never be patched. It now gets the frames and box the router gives
it (`net_frames`). The current run's `sci/cu` ("stays partly-connected whatever I move",
`FRICTION.md` of 20261030-2352-opus) re-routed on every build to the same half-joined route; it
now patches (`~sci/cu/b17 extended, 6 belts, 1 inserter`) and red2 gets copper.

## Moved ends, and machines on a standing belt

- A belt net whose end moved (a chest one tile over) goes to the patch instead of being laid
  again. When no consumer is reached any more, the patch keeps the trunk its drivers feed
  (`route._trunk`), branches each consumer off it where it stands, and takes up the old end's
  tail. Fluid nets still route again on any change.
- When the new layout takes a tile of a belt net, only the carriers on taken tiles are dropped and
  the rest goes to the patch (was: the whole net laid again).

Replay on the current run's J1 (`world-j1.fk` with the steel row on the main coal net, on
`world-i.fkp`), with fe_box4 and st_box each moved one tile: fe_pl4 keeps 141 of 141 carriers
(was 137 belts laid again), and every net is patched; `report_checks` 43 of 43 nets connected,
0 SPILL. The coal case the player saw re-route on cc1af12 already patched on 2.0.73.

## Not done here

- No search for a branch from a driver machine itself (a second inserter off a requester chest):
  a short feed (chest, inserter, two belts into a port) has no place for a splitter and is held.
- A trunk cut by a new machine is not re-joined across the cut: its consumers past the cut get new
  branches from the piece their drivers still feed.

## Tests

`test_route_keep_2074`: a new module's port patched into a standing world net, and a moved chest
patched with the trunk's belts kept. Changed for the new behaviour: `test_route` (a belt net that
can't be patched is held), `test_lanes_pairs` (a lane pair the same), `test_friction_2062` (a port
net gaining a consumer inside a sealed module is patched), `test_flow` (a moved chest and a moved
lab row are patched). Full suite: 1120 tests OK.
