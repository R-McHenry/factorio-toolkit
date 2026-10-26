# Toolkit 2.0.38: every sealed module's contract, the four-rib example and the docs (phases 4 and 6)

Rory, 2026-10-25: phase 4's contract report and phase 6's docs and example. A sealed module is now a
thing you can read a contract from and a thing the docs teach with a worked design.

## `fk contract FILE`

```
contract bus4ribs: 4 sealed instances
  rib0: out iron-gear-wheel 1.0/s via box0/c0 (got 1.0) | in iron-plate 2.0/s via bus tap n7 (got 2.0)
  rib1: out iron-gear-wheel 1.0/s via box1/c0 (got 1.0) | in iron-plate 2.0/s via bus tap n13 (got 2.0)
  rib2: out iron-gear-wheel 1.0/s via box2/c0 (got 1.0) | in iron-plate 2.0/s via bus tap n19 (got 2.0)
  rib3: out iron-gear-wheel 1.0/s via box3/c0 (got 1.0) | in iron-plate 2.0/s via bus tap n25 (got 2.0)
```

One line per sealed module, one part per port: the direction, the item, the rate the module needs (an
`in` port: its consumers' appetite) or makes (an `out` port: its drivers' potential) at full speed,
**where it crosses** (naming the bus port and its tile, or the machine at the far end), and **what it
actually got** in the rate model. Generated from the model, never written, so a starved rib reads its
2.0/s contract against `(got 0.4)`; `fkcore.contract` also resolves both sides of a port when the
pool's number lands on either net.

## The example: `agent/docs/examples/bus4ribs.fk`

The canonical shape: one 4-belt iron bus, four sealed `GearRib`s (plates in at the west port, gears
out at the east one), one mouth feeding the bus, one provider chest per rib. The bus binds its ports
by list — `in1: feed, r0: rib0.iron, …` — so the taps' positions come from the list order (`n7`,
`n13`, `n19`, `n25`). It checks clean (22 machines, 18 nets, 0 check lines), lays out at 78x25 with
no invariant failures, and routes all 17 nets with no failure, no `LEAK`, no `SEAL`, no `PORT`.

## LANGUAGE.md

A "Modules with ports (sealed)" section: the `port` declaration and lanes, `size`, the port tiles and
their free approach tiles, the sealing rules (`SEAL`, `PORT`), the bus's connection list (a named net
per port, mouths `in1..inN`, staircases in order, `left`/`right` kinds), and the contract with the
four-rib example's own output.

## Verified

- `tests/test_contract.py` (4): the four-rib base prints four lines with the right taps and rates; a
  starved base (2/s for four ribs) shows every rib's `(got 0.4)` and the four sum to the 2.0/s the
  feed brings; a portless module has no contract line; the docs example prints four lines.
- The example's own numbers above; the full suite keeps only the same 170 pre-existing failure/error
  lines as the 2.0.27 tree, and the elaboration baseline is unchanged.

## Not in this slice

`--module X` (the patch scope that rebuilds X's frame plus the parent segments ending at its ports,
keeping everything else standing) is the rest of phase 4; the `.fkp` port record from the plan's §5.3
and the surface link are phase 5's.
