# Toolkit 2.1.6: settings changed in place

Plan: `assessment-20261031\PLAN-2.1.md`, "Settings changed in place (Rory, 2026-10-31)", and
phase 4 of "Order".

Until now a changed setting (a condition, a filter, a chest bar, a request) meant the entity was
ordered out and robots laid it fresh. Now the paste writes most settings onto what stands, a tier
change is an upgrade, and a wire pass makes the wires match the design.

## Measured on a laptop server

Factorio 2.0.77, `build_blueprint` superforced over standing entities.

- A field the blueprint leaves out is cleared: requests, trash and buffer flags, a chest's bar, a
  storage chest's filter, an inserter's filters, a combinator's settings.
- A `control_behavior` at the game's defaults (`{}`, or `circuit_enabled` false) is ignored.
- With no `control_behavior` at all, a wired machine keeps its own conditions.
- A `control_behavior` that differs from the defaults in any field is written whole.
- A mining drill, a burner drill, a pumpjack and an offshore pump take nothing from a paste.
- A paste over another entity of the same fast-replace group and the same size orders an upgrade
  itself. `order_upgrade` before the paste works too: the paste then writes the new settings onto
  the entity being upgraded, and the upgrade keeps them, with wires and contents.
- Upgrades the game accepts: inserter to fast to bulk, burner inserter to inserter, assembler
  1 to 2 to 3, belt, underground and splitter tiers, all chests (wooden, iron, steel, passive,
  requester, storage), stone to steel furnace, small to medium pole.
- Upgrades it refuses: inserter to long-handed (another group), steel to electric furnace (size),
  medium to big pole, pipe to pipe-to-ground, belt to underground, burner drill to electric drill.
- A robot-built pole joins every standing pole in reach that its own paste didn't lay. Within one
  paste it adds no extra wires.
- Reading every wire of 27,000 entities takes 0.12 s.

`fkcore/settings.py`'s docstring keeps these results.

## Every setting is written

- The codec writes `control_behavior` on every inserter, belt, assembler, furnace, pump, lamp,
  power switch, train stop and agricultural tower. When the design sets none, it writes the reset
  (`codec.RESET_CB`: off, a condition with no signal). So a paste clears a hand-set condition.
- Reading a blueprint back drops the reset, so a design reads the same as before.
- Drift counts an explicit default as the same as an absent one. The defaults the game exports
  are dropped too: a belt's read mode 0, a lamp's colour signals, a drill's resource reading, a
  whitelist filter mode, `is_on` true, a condition with no first signal.

## Three ways a change reaches the world

The apply report says, for each change, how it gets there and why:

    written in place 1 (the paste sets them on what stands): i1 (the design changed its settings)
    upgraded 5 (robots swap them; settings, wires and contents stay): m0 assembling-machine -> assembling-machine-2; ...
    laid fresh 1 (ordered out, and robots lay them new): i2 (inserter stood there, not in the design entity's fast-replace group)

- **Written in place:** a changed setting, or one set back from a hand edit. Nothing is ordered
  out.
- **Upgraded:** another tier in the same fast-replace group and the same size. The apply orders
  the upgrade, then pastes.
- **Laid fresh:** a drill or offshore pump with new settings, a ghost, another kind of entity, a
  turned one, or a swap the game refuses.

A partial apply (`--keys`) now lays, and keeps, the whole design's pole wires, not only those of
the rows it pastes.

## Wires

After each paste, after `fk wait` and on each later apply, a wire pass reads the wires in the
area and edits them to match the design:

- it adds the design's red, green and copper wires that are missing;
- it cuts wires between design entities that the design lacks;
- it leaves wires to anything outside the design alone (another plot's pole, a world pole);
- it says one line, `wires: 3 added, 1 cut`;
- a circuit wire made by hand is named once as `by-hand` before it is cut.

The pass is `fkcore/wires.py`. It reads with `get_wire_connectors`, and edits with `connect_to`
and `disconnect_from`, 30 to a call. It registers nothing.

FAIR-PLAY.md gets a line: wires may be added and cut by script.

## Checked on a laptop server

`python tools/laptop_server.py NAME` (Factorio 2.0.77, 2026-10-31):

- **defaults:** a wired inserter, fast inserter, belt, furnace, pump and lamp with hand
  conditions, pasted with nothing set. With the 2.0.78 codec they keep the hand conditions. With
  this one all are cleared. The drill keeps its settings either way, so it is laid fresh.
- **settings:** 8 hand edits named. The apply wrote 7 in place, ordered nothing out, laid no
  ghost, and said `wires: 0 added, 1 cut`. Every setting came back, and the diff found nothing.
- **robots** (play mode, robots build): two plots and a world pole. After the second plot's build
  the pass said `wires: 1 added, 1 cut`: it cut the robot's join to the other plot's pole and
  added the design's own wire. Then a second design: 5 upgraded, 1 written in place, 1 laid fresh
  (long-handed), 1 hand wire cut. After the robots: a fast inserter with its new condition, an
  iron chest still holding 30 plates, an assembler 2 with its recipe, fast belts. The diff found
  nothing but the world pole.
- **own** and **turned** still pass.

## Not in this release

- A drill, pumpjack or offshore pump with new settings is still laid fresh.
- `laptop_server.py ghosts` fails, with or without this change: the lab paste lands even
  uncharted.
- The golden check covers netlists, not blueprints. Blueprints now carry the reset on every
  machine that sets nothing.
