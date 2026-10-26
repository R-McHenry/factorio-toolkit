# Toolkit 2.0.40: three fixes to sealed modules (the plan review, 2026-10-26)

Rory, 2026-10-26, on the review of 2.0.28–2.0.39 (`assessment-20261025\PLAN-GLOBAL.md`):
"Go ahead and try and implement the quick fixes ... I agree with all your changes." These are the
three that had to land before plots become sealed modules.

## 1. A parent net routes around a sealed child

`route_layout` freed a sealed module's **whole** frame for its own nets, and with it the frames of
everything inside: its template rows (the empty tiles kept for poles) and any sealed child. A sealed
`Outer`'s own net from its west port to a chest east of its sealed `rib` ran straight across the rib:
twelve carriers inside the rib's frame, reported only afterwards as `SEAL`.

Now only the frames of the modules the net is inside are free; every other instance's frame stays
blocked, as it is for a net outside. The same design routes around the rib with no `SEAL` line.

The sealed set is now `flat.sealed` everywhere (route, `SEAL`, `PORT`, `--module`). The router and
the checks had asked "does any port key start with this path", which also counted the ports of a
sealed module *nested* inside a transparent one.

## 2. `size` seals a module

A module that declares `size WxH` is sealed, ports or none. A block with no ports is closed: refs
into it are refused, its nets route inside its frame, and only robots reach it. This is what a plot
needs: a factory that connects to nothing must keep its isolation. No existing design declares
`size` without ports, so nothing that exists elaborates differently. A module with neither stays
transparent, as before.

## 3. `FRAME`: contents past the declared size

`seal_checks` also reports a sealed module's own entity (a machine, a template's belt, a child's
contents) that stands outside its frame:

    FRAME     rib/g/outb0 (transport-belt) is part of sealed module rib but stands outside its frame
              40,10..55,15: grow its size or move it in

(the four-rib example's `GearRib` declared `size 16x6` instead of `16x10`: four such lines)

It is the old "outside plot" check, moved to modules. 2.0.37's missing assembler was this kind of
mistake, reported then only through its symptom (the port's approach tile under the machine).

## Verified

- `tests/test_modules3.py`, `FixesTest` (4): the nested design routes with no carrier of the parent
  net inside the child's frame and no `SEAL`/`FRAME`; `size` alone seals (in `flat.sealed`, a ref
  into it refused, its nets routed with no `SEAL`); a module with neither stays transparent; a rib
  declared too short for its row gives `FRAME` lines.
- The full suite: 945 tests, OK (941 before, plus these four).

## Not in this release

The rest of the review's plan: whole-belt ports and recorded port tiles, then the root design (plots
as sealed instances), root routes between plots, rates across the world, migration and the lab test.
`PLAN-GLOBAL.md` outlines them.
