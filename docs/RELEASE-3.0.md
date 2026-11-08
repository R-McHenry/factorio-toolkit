# 3.0: the player owns the build

3.0 is the build model of PLAN-3.0 (`assessment-20261101\PLAN-3.0.md`), built 11-01..11-02 on
`claude/30-build` and released 11-08 by merging that branch onto main 2.1.34. The language stays
2.x; what changes is what a command is, what is kept between builds, and what unit the router
works on.

## What changed for the player

- **Every step is a command.** `fk route NET[,NET]`, `fk place`, `fk report KIND` run one step of the
  build script alone, nothing pasted (`python -m fkcore step SCRIPT STEP`). `fk route --try X,Y X,Y`
  asks how a belt would go, laying nothing.
- **The design database on disk.** The route step writes one file per net as it lands
  (`out\design\<factory>\nets\`). A build that stops or fails keeps every net it finished, and the
  next build starts from them. `fk status [NET]`, `fk hold NET`, `fk unhold`, `fk unroute NET`; a net
  held while a build runs is taken as it stands when the router reaches it.
- **Each net routes once.** No more rip-up passes over every net: one pass in order, a failed net
  gets a group try (the nets in its way laid again with it, on a 3 s budget), then one promoting
  search. A net that failed on the same ground last build is not searched again (`route --again
  NET`, `--retry-failed changed|always|never`).
- **The routing policy is the build script's:** `route --group-budget S --group-max N --first
  NET,... --skip NET,... --area X0,Y0,X1,Y1 --failed keep|drop`. A skipped net is reported `manual`,
  never a failure.
- **`later:`** in the build script: the steps after it run after the paste and never stop it.
- **Background builds:** the player's `fk build` returns at once, its lines in `game\out\build.log`;
  `fk build --wait` for the old way.
- **Seeds and routing pieces:** `fk seed NET 'splitter X,Y S'` pins a piece of a net and the router
  lays the rest through it; `game\routing.fk` (Waypoint, Merge, Split, InlinePump) are sealed
  modules the player imports and reads.
- **Chained nets:** `net N: a -> piece -> b`, `inout` pass-through ports.
- **Sealed modules compile once (design database):** `fk compile MODULE`, `route --reuse-lab`;
  stored insides in `out\design\modules\<module>\<key>.fkp`.
- **Literal ports**, drills dropping to the side in cells, drops onto underground exits, k
  inserters on a machine one hand can't keep up with, a chest loading its belt from several sides.
- **`Pump<fluid>`**, `pipe-too-long`, `route --pipe` (pipe material).
- **`fk walk`** (the net walker), **`fk catalog learn`** (a run's own catalog overlay for modded
  and Space Age machines), **`fk map`**, Sea Block packs and Bob's adjustable inserters.

## The merge onto 2.1.34

Main went 2.1.31..2.1.34 (the megabase lab work and the Rust router kernel) while 3.0 was on its
branch. Both lines changed the router:

- **Routing units.** 2.1.31 split `_route_layout` into compile units (each sealed module's own nets
  on their own, innermost first, twins and the router's compiled store `out\compiled`). 3.0
  replaced the passes with route-once. 3.0.0 keeps the units and routes inside each with 3.0's
  algorithm; a group try lifts the nets of its own unit and of the units nested in it (a top-level
  net past a routing.fk Waypoint may lift the Waypoint's belt, laid again in its frame), never a
  sibling unit's, so one module's failed net never rips up another module's routes. `FK_NEGOTIATE=1` still negotiates and then runs the 2.1 passes per unit.
- **Two compile-once stores.** 3.0's (the design database, `fk compile`, per module name) runs
  first and pins what it holds; main's (in the router: twins in one build, a 180-degree twin, the
  keyed `out\compiled` store the megabase bays use) takes what is left. Joining them is open.
- **The Rust kernel.** fkroute mirrors the 2.1 search. Where 3.0 searches differently it falls back
  to Python: a tap sink with adjustable arms, one that wants k > 1 taps (states that count them),
  and every tree laid reversed (`drop_taps`: 3.0 lets an underground exit take a drop). Everything
  else still runs in Rust, and `FK_NATIVE=check` still compares the two.
- Both lines fixed diamond imports (one parse a file); main's code stays.

## Open

- One compile-once store instead of two.
- The Rust kernel learning 3.0's tap rules, so those searches leave Python.
- PLAN-BUILD (`assessment-20261108\PLAN-BUILD.md`): blueprints, paste and placements, per-placement
  look and diff, adopt into source, checks the script asks for.
