# Toolkit 2.0.28: module ports, sealed by declaration (PLAN-MODULES phase 1)

Rory, 2026-10-25: "instead of having 'across' nets, it should be inferred from the code being modular
and api defs essentially telling it that its a port like vhdl." This is phase 1 of
`PLAN-MODULES.md`: the language grows ports and `size`, a module with ports becomes a sealed
component, and nothing that exists today elaborates differently.

## The three answers this release is built on

1. **A ref past a sealed module's ports is refused at elaboration.** The message names the ports the
   module has and the `port` line to add. Sealing is not advisory.
2. **The port tile is chosen facing the port's partner and then recorded.** `@w` gives the edge;
   `@w4` pins the tile. (The record in the `.fkp` is phase 3, with routing.)
3. **`@beside` is dropped.** For phase 2, the bus's connection list, written in order, *is* the
   order of its ports — a VHDL port map, direction from the netlist, bands spaced by staircase
   width with `length` following, the first N loads straight onto one belt each, and an `ORDER`
   warning instead of hand-numbered taps. Recorded in `PLAN-MODULES.md` §4 and §10; not implemented
   here.

## The statements

```
module GearRib size 24x10 {
  port iron : in  iron-plate      @w      # the build picks the tile facing the partner
  port gear : out iron-gear-wheel @w4     # or the designer pins it
  gears = AsmRow<n=2, recipe=iron-gear-wheel> @(4, 2)
  net fe: iron -> gears                   # inside, a port is an ordinary endpoint
  net g:  gears -> gear
}

gears = GearRib @(30, 10)
net fe: bus -> gears.iron                 # outside, it is the module's endpoint
net g:  gears.gear -> chest
```

- `port NAME : in|out|inout ITEM[, ITEM] @SIDE[POS]` in a module body; `@SIDE` is `n`, `e`, `s` or
  `w` of the module's frame, `@w4` the tile along it. A lane pair is written `iron-ore | coal`.
- `size WxH` on the definition is the frame: `_module_frame` returns it as written, so a port list
  has a frame before anything is placed. Without `size` the frame is measured from the children, as
  before.
- **Direction is the module's own**: `in` is fed from outside and feeds inside, `out` the other way,
  `inout` both.

## Sealed by declaration, transparent otherwise

- **A module with ports is sealed.** The nets written in its body are local (their scope is the
  instance path), the rest of the design reaches it only by a port's name, and a ref that goes
  deeper — `gears.gears`, `gears.gears.m1`, or a bare `gears`/`gears.*` — is refused:

  ```
  t.fk:13: rib.gears: rib is a sealed module (GearRib), and its ports are iron (in iron-plate);
  gear (out iron-gear-wheel). Name a port (e.g. rib.iron), or add one to module GearRib:
  `port NAME : out ITEM @SIDE`, and give it a net inside
  ```

  The suggested direction comes from how the net would use it: a driver wants `out`, a consumer
  `in`.
- **A module without ports is exactly today's behaviour.** Every existing `.fk` is transparent and
  keeps its flat refs (`mall.belts`, `iron.smelt`); there is no `across`, no flat mode, and no
  migration to write.
- A port is per instance: instantiating `GearRib` twice gives `a/iron`, `b/iron` and two sealed
  frames, not a shared interface.

## One net in the source, two in the netlist

A crossing net meets itself at the port, and the rates model sees it as one net: the port's machine
is a conduit that makes and takes its items at no rate, so `rates._pools` joins the inside net and
the one outside that names it (a zero-length continuation). With the example above, `fk rates` solves
the smelter's supply into the rib's assemblers and `UNDERFED` names a rib that is not fed, exactly as
it would through a bus.

## The `PORT` check (warn, never gate)

- a port no net names, or one side of it not wired (inside or outside);
- a use against its direction (an `in` port driven outside, an `out` port consumed outside);
- items that disagree with the net that names it;
- a declared item carried on one side and not the other ("nothing outside brings coal to it");
- `@n30` on a module `size 24x10`: the edge runs 0..23;
- a port name taken by an instance in the same module, or declared twice, is refused — an interface
  and a body cannot share a name.

## Tests

- `tests/test_ports.py` (23): the statement and its refusals; a crossing net split at the port
  (`ore` consumes `rib/iron`, `rib/fe` drives from it); rates pooled through the port with the rib at
  full speed and no `UNDERFED`; the refusal message names the ports and the line to add; bare/star
  refs and a port's "inside" refused; per-instance ports; a sealed module reached through a
  transparent one; transparent module refs unchanged; every `PORT` line; the declared frame.
- `BaselineTest`: the digest of every `.fk` in the repository (42 designs: `agent/docs/examples`,
  `games`, `kickoff/template/game`, `tests/data`) against
  `tests/data/elaboration-baseline.json`, generated from **2.0.27's** elaboration before this change.
  Every machine, net and check line is unchanged, so the migration promise is tested, not asserted.
  Regenerate the baseline only when elaboration is meant to change.
- The full suite (876 tests) has four order-dependent failures (`test_bus` capacity, the committed
  `.fkp` signature, two lane pairs) and the sandbox's temp-dir errors; a worktree at 2.0.27's
  `7968802` produces the identical 170 lines, so none of them is this release's.

## What changed in the code

- `lang.py`: `port` and `size` (a `dim` token for `24x10`); `Port` and the fields on `Module`; a port
  in the file body is a syntax error (it is a module's interface).
- `elaborate.py`: `PortInst`, `flat.ports` and `flat.sealed`; a port machine per instance; `_resolve`
  refuses a ref past the ports and resolves a port's name; `FlatNet.scope`; the `PORT` check; the
  netlist split and the item-mismatch line.
- `rates.py`: `_pools` joins the two nets of any port by item (bus ports unchanged); an absorbed net
  ending at an `in` port passes its supply on.
- `expand.py`: a module that declares `size` has that frame.

## Not in this release

Phases 2–6 of the plan: the bus port map (answer 3 above), port tiles recorded in the `.fkp`, routing
a sealed module inside its frame and the `SEAL` check, the contract report and `--module` scope, the
surface link, and the player docs/example. **A port design organizes and rates today but does not
route through its ports yet** — do not build one. Run 1343 is pinned to 2.0.25 and sees none of this;
it lands for a future run.

Two phase-2 points the answer opens, reported rather than decided here: what a connection list
*generates* (the nets between bus port k and each named endpoint), and the rate model's per-belt story
once the first N loads each feed one belt (`CAPACITY` and `OPEN` assume every load reaches every
belt).
