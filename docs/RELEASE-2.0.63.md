# Toolkit 2.0.63: DNP, do not populate

Rory, 2026-10-29: "it should be a DNP basically. So you can DNP any part of the design in order to
destruct it and nullify any production, power coverage etc that it provides in the model, but it
is still visible to placement and routing. That makes it easy to temporarily delete stuff ... It is
also a great way to implement a scaling row." On taking up what stands: "--confirm makes sense I
think, as long as it's just a flag and not an extra step to confirm".

## In the language

| written | what is DNP |
|---|---|
| `X = Assembler<recipe=..., dnp>` (or `dnp=1`) | that instance, any kind, a module included |
| `dnp mall1, sci3.packs` | a body's line naming instances at any depth (an unknown name is refused) |
| `Stack<cell=C, n=12, built=8>` | cells 9 to 12: laid out and routed, not built |
| `Stack<cell=C, n=12, built=auto>` | the size step chooses how many of the 12 to build, as `n=auto` would |

A DNP instance's whole contents are DNP (`Flat.dnp`, `Flat.is_dnp`).

## In the build

- **The model.** A DNP machine runs at duty 0, so it makes, takes and asks for nothing.
  - `report_rates` gives its binding as `dnp: not built`, and adds a line with what the DNP
    machines would make at full speed.
  - The size step doesn't count it as free to grow.
  - Elaborate drops checks about DNP pieces.
- **Placement and routing.** Unchanged: a DNP piece keeps its tiles, and nets route to it.
  Turning a piece on or off moves nothing. The test turns `built=2` into `built=3`, then drops
  `dnp gears`, and gets the same 86 entities each time with every route kept.
- **What isn't built.** After `route`, each build tags `dnp` afresh (`route.tag_dnp`).
  - Tagged: every entity of a DNP instance, and every route carrier that serves no live
    driver-to-consumer pair. That covers a branch or an inserter to a DNP machine, and a net whose
    live ends are gone.
  - Not tagged: a trunk that still feeds a live machine.
  - `route.txt` says `dnp N entities laid but not built (DNP: ...)`.
- **Power and robots.** A DNP pole or roboport covers nothing, and a DNP chest asks for no robots.
  What a DNP piece would power still gets its poles, so they're ready when it's built.
- **The paste.**
  - `apply.scope_rows` leaves DNP entities out, and `report_bom` never counts them.
  - The diff area still covers them, so what stands there is judged.

## In the game (`sense`)

| what's there | verdict | the apply |
|---|---|---|
| nothing | `dnp`: as designed (counted, not listed) | nothing |
| a ghost of it | `unowned` | cancels it |
| built | `dnp-standing` | keeps it: "fk build --confirm takes it up" |
| built, and `fk build --confirm` | `unowned` | orders it out |

`fk build --confirm` passes `--confirm` to the script's `diff` and `apply`. The apply report gives
`dnp: N kept standing` or `dnp: N ordered out`.

## `fk dnp`

`fk dnp world.fk NAME[,NAME] [--off]` writes the file's `dnp` line, or takes names off it. It
elaborates the result and puts the file back if a name matches nothing.

## Checked

- **Live lab.** `lab-demos/dnp`, slot 2000,1000 (`/lab` at 2030,1020), on toolkit `e4234ee`: a
  6-cell furnace column with `built=3`, and a gear assembler DNP'd by a line.
  - 105 entities laid out, 75 pasted and revived.
  - The diff says `dnp 30, ok 75`.
  - `report_rates`: "col/3, col/4, col/5, gears ... at full speed they'd make iron-plate
    112.5/min, iron-gear-wheel 60.0/min".
  - The measure read 0 ticks, because the live game is paused (the opus player's pause).
- **Tests.** `tests/test_dnp.py`, 13 tests:
  - the model;
  - laid out but not built;
  - the scaling row growing in place;
  - the refusals;
  - the flag and the dotted line;
  - `built=auto` (5 of 12 for an assembling-machine-2 on gears);
  - a DNP pole in the cover;
  - `fk dnp`;
  - the four game verdicts, and the apply taking it up only with `--confirm`.
