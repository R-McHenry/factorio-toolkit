# Toolkit 1.2 (2026-10-20)

The second point release of the V1 toolkit: what 1.1 left open in the 0534 run's FRICTION.md. As
in 1.1 there are no new rules: the build does more by itself, and the reports say what it did.
All six items are fixed, each with tests; none is deferred.

## New

- **The toolkit's own entities** (the run: `watch plots: keep` kept the toolkit's own dropped
  rows, and the new rows came out MISPLACED; a moved plot left 166 entities standing outside every
  plot, a shrunk one its cut-off part; an emptied factory lost its entities and kept its 28
  ghosts). The world can't say what the toolkit built (robots build a pasted ghost with no
  last_user), so the toolkit remembers: `game\out\own\<surface>.json` holds every entity the
  applies pasted, with a carrier's net (`fkcore.own`). An entity of it that the design no longer
  holds is `NOBODY` ("the toolkit's own, dropped from the design: the next apply removes it")
  whatever `watch` says, unless a claim or a mark covers it or a player touched it. The apply
  orders it out before the paste, an unbuilt ghost too (a diff names a ghost by the entity it
  stands for, so a NOBODY ghost was never found before; the game removes a ghost ordered out at
  once), and with no `--area` its scope reaches the dropped entities wherever they stand. The
  record is seeded once, when there is none, from the .fkp files last written (write_layout, before
  it writes the new ones), so a run from before 1.2 starts from what it built.
- **A carrier laid fresh when its net changes** (the run: old items stayed on belts re-laid on the
  same tiles, old petroleum in re-laid heavy-oil pipes; the player moved items by script, and 1.1's
  `fk fresh` took such belts up by hand). A carrier the record shows under another net that holds
  what its new net doesn't carry is ordered out before the paste, and the paste lays a fresh ghost
  on it: robots take the old one up with what it holds and build the new one, in one build. The
  snapshot now reads the fluid in pipes, so `WRONG_ITEM` and `fk fresh` cover pipes too. `fk fresh`
  stays for stale items without a net change.
- **A moved endpoint makes its net's route stale** (the run: `cu` moved one tile, place said
  stale, route kept copper pinned, UNROUTED). `route --only stale` compared only belt end tiles; a
  chest's end is a machine its inserter reaches. It now compares everything a route is laid to,
  per role (belt ends with their headings, the machines it inserts into or picks from), and
  `out\route.txt` says which ends moved.
- **`cover robots` and the surface's network** (the run: a factory inside the kit roboport's square
  got a roboport of its own from a stock of 4, and the player turned the step off). Chests the main
  network reaches (the kit's roboport and every roboport joined to it, as NO_ROBOTS judges it) need
  no roboport. Each roboport the step places gets a storage chest beside it (`robots/s<k>`), so
  what robots take up far from spawn is stored there (the run's big rebuild flew every item 110
  tiles); `cover robots --storage none` leaves it out. The step also keeps its roboports and chests
  off water and cliffs now, as `cover power` does.
- **A new plot over the old power bridge** (the run: INVARIANT shared infrastructure stopped the
  build). With `floorplan --bridge-power` the plot takes the bridge's own poles, and the bridge is
  laid again around the plots. Other shared infrastructure in a plot still stops the build.
- **`fk lua` takes any chunk** (the run: a 13 kB chunk with single quotes failed with "unexpected
  EOF while looking for matching"). Git for Windows' ssh, an MSYS program, gets at most about 8 kB
  of one argument (12 854 characters in, 8 186 out on the laptop); the chunk now travels on ssh's
  stdin to `fkcore lua . --file -`. And it goes to the game as written: the link joined a chunk's
  lines with spaces, so a comment at the end of a line took the rest of the chunk with it.

## Also in 1.2

- **Steam power in the player docs**: the boiler and steam engine geometry in LANGUAGE.md and a
  3.6 MW plant in EXAMPLES.md (`docs\examples\steam.fk`). The templates were there since the
  fluids work; built offline in play mode it routes clean, coal by belt into each boiler.
- **Notes from run to run** (Rory, 2026-10-20): the player keeps `NOTES.md` in its folder, and a
  kickoff copies the newest one into the next run (`new_run.py --notes`); the brief and CLAUDE.md
  point to it.

## The player's side

TOOLKIT.md says it in plain words: a build takes back what it built and the design no longer has;
a belt or pipe re-laid under another net is renewed by the build; a net is routed again when an
end moves; `cover robots` adds a roboport (and a storage chest) only where the network doesn't
reach yet; a plot over the bridge re-lays it; `fk lua` takes long chunks with comments. The brief
says the same in three places ("Mistakes are cheap", "Ways to get unstuck", "Keep the base tidy").
No new rule anywhere.

## Checked in the game (a laptop test server, never the live game)

- A superforced paste over the same belt already ordered out places a ghost on it and keeps the
  order; over the same belt not ordered out it places nothing. `order_deconstruction` on a ghost
  removes it. The snapshot reads `petroleum-gas` and `water` from a pipe and a pipe-to-ground.
- `python tools/laptop_server.py own` runs fixes 1 and 2 through `fkcore.apply` in play mode: a
  dropped built assembler is ordered out, a dropped ghost is gone, and a belt laid under another
  net with the old net's plates is ordered out with a fresh ghost on it; the diff after it reads
  the ghost as the design's and the old belt as NOBODY "ordered out: robots take it up".
- `/sc` takes newlines: a 40 kB chunk went through one RCON command.

## Compatibility

The 0534 run's game code (a copy; the live run untouched), through the 1.2 design steps, writes
the same 17 .fkp files byte for byte as 1.1.1 does and as the run committed, and the same reports
but for one line: write_layout seeds the record with 2487 entities. So its next build rips nothing,
and what 1.1 left standing MARKED stays as it is (it isn't in the record). With `cover robots`
back in its build script, 1.1.1 would place 3 roboports (oil, stone, iron2) and 1.2 places none.
357 tests pass (332 at 1.1.1).

## Handing it to a running run

Deploy it on the host as `fk-v5-SHA` first: the new `bin\fk.py` sends `fk lua` chunks to the
host's `fkcore lua --file -`. Then `kickoff/upgrade_run.py RUN --sha SHA` (only with Rory's
approval) swaps the toolkit, bin and docs; nothing in the run's game files changes, and the record
starts at the next build. It prints the note for the player (a Claude player gets it through
`INBOX.md`), which says `cover robots` can go back in its build script.

## Found on the way, not done

- The record lives in `game\out\own\`: deleting `out\` forgets what the toolkit built, and the next
  build seeds it again from the .fkp files (a row dropped before that is a foreign change again).
- `cover robots` lays factories out one by one: a roboport placed for a later factory does not
  count for an earlier one in the same build.
- The toolkit's own Lua builders still go through `Rcon.lua`, which joins lines; none of them has
  a comment at the end of a line.
