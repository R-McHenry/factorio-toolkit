# Toolkit 2.1 (draft): open circuits

Plan: `assessment-20261031\PLAN-2.1.md`, "Circuits that reach any building (Rory, 2026-10-31)",
and the open-circuits phase of "Order". The integrator gives the number.

Until now a wire could reach only what the toolkit modelled, `set` took six properties, the
signals were lists copied into the codec, and a wire longer than 9 tiles was a `wire-too-far`
line. Now a player can wire and set up any building from source.

## Raw settings

- `set X: cb.FIELD=VALUE` writes one field of the entity's control behaviour, named as the
  blueprint names it: `cb.read_robot_stats=true`, `cb.circuit_condition="iron-plate<50"`.
- `set X: bp.FIELD=VALUE` writes any other blueprint field: a speaker's `parameters`, a display
  panel's `text`, a lamp's `color`, a train stop's `station`.
- Both work as an instance's parameters too, and as a kind's.
- A value is JSON-ish:
  - a number, `true` or `false`;
  - a string in double quotes (no escapes, so no double quote inside), or a bare word;
  - an object `{key: value, ...}` (keys are words or quoted strings), or a list `[value, ...]`;
  - it can span lines.
- Two conveniences, at any depth:
  - a string in a signal field (`*_signal`, `*signal_id`, `signal`, `icon`) becomes the game's
    signal, typed from the game's list;
  - a string in a condition field (`*condition`) is `S<N` or `S>=T`, as `if=` takes it.
  An object is taken as written.
- The typed properties stay as the short form. Where a typed property and a `cb.` field write
  the same field, the `cb.` one goes in the blueprint, and a `CIRCUIT` line says so.
- A `$name` inside a quoted string is left as written, for module parameters.

Inside:
- The layout keeps them as two entity attrs, `cb` and `bp`, each a JSON object in the game's form.
  The `.fkp` quotes them.
- `codec.made_fields` puts the `cb` fields into `control_behavior`, over the typed ones, and the
  `bp` fields on the entity. A machine with a raw `cb` gets no reset.
- They ride in `tags.fkp` and come back on reading, as the typed settings do. If the game's
  fields differ, the game's win, in `config`.
- `own.settings` counts them, so a changed raw setting is a changed signature.

Refused:
- `CIRCUIT`: `bp.` on a field the build writes (`name`, `position`, `direction`, `recipe`, `tags`,
  `wires`, `type`, `control_behavior`); a field set twice to two values; a condition string that
  isn't one.
- `no-signal`: a signal the game hasn't got; a parameter signal or `signal-unknown` anywhere; a
  wildcard in an output signal (`*output_signal`).
- A module instance takes none: elaboration already refuses any parameter but `duty` and `dnp`.
- Syntax errors: a field that isn't a word of letters, digits and `_`, a key given twice, a key
  that isn't a word or string, a value that isn't one of the above.

## Drift sees raw fields

- `fkcore.settings` compares the design's `bp.` fields where the design sets them. `cb.` fields
  are part of the control behaviour, compared whole as before.
- The game's defaults for the new buildings are dropped like the others: a roboport's five output
  signals (X, Y, Z, T, R) and a speaker's `circuit_parameters` at instrument 0, note 0.
- Numbers compare to 6 decimals. The game keeps a volume or a colour as a 32-bit float, so 0.8
  comes back 0.800000011920929.
- A hand edit reads in the source's terms: `bp.parameters={...}`, `cb.circuit_parameters={...}`.

## Kinds carry raw settings: four presets in the prelude

`fkcore/prelude.fk` (and the kickoff template's copy) gets:

| kind | is |
|---|---|
| `RobotCounter` | a roboport with `cb.read_items_mode=0, cb.read_robot_stats=true`: its robots on its wire (X/Y logistic, Z/T construction, R roboports) |
| `ColourLamp` | a small lamp with `cb.use_colors=true, cb.color_mode=1`: colour from signal-red/green/blue |
| `Alarm` | a programmable speaker: global siren (instrument 0, note 6), an alert on the map with a `signal-alert` icon and "Alert" |
| `Display` | a display panel, always shown, on the map too |

The instance's own field wins over its kind's, field by field.

## Signals from the game

- `codec.py`'s virtual signal and fluid lists are gone. `facts.signal_type` types every signal
  from `facts.json`: virtual, item, fluid, entity, recipe, quality, space location, asteroid
  chunk. A name that is several is the item. An unknown name is an item, as before.
- `circuits` knows every signal the game has: `signal-alarm`, `fusion-plasma`, a recipe, a
  quality.
- `NON_TRANSMITTING` (the parameters, `signal-unknown`) comes from the game's list; it is refused
  anywhere, as before.
- New: a signal that never goes out on a wire (`signal-each`, `-anything`, `-everything`) is
  refused where one is sent: a `Constant`'s signals, a reactor's reading, a raw output signal. A
  condition still reads with a wildcard.
- The auto pool (`signal x`) is the game's virtual signals, so it has more of them. No design in
  the corpus leaves a signal to the build.

## Any building with a connector on a wire

- A `wire` end can be any instance whose building has a circuit connector in the catalog: an
  `Entity` of any kind, a roboport, a pump, a lamp, a speaker, a display panel, a train stop.
- A building without one (a pipe, a beacon) is a `no-wire` line, and gets no wire.

## Wires carried on poles

- A wire net is still a minimum spanning tree over its entities. An edge longer than both ends'
  reach now hops along poles:
  - the layout's poles that carry no other net of its colour cost nothing;
  - a new pole on a free tile (inside the frame, on no entity, no terrain keep-out, within 6 tiles
    of the box around the two ends) costs one;
  - the fewest new poles win, then the fewest steps, then the shortest.
- New poles are `circuit-poles/p1`, `p2`, ..., the power cover's pole (else a medium pole), under
  a `cover circuit-poles wires` record. Each build takes them out and lays them again, so they
  follow the design.
- The report says it: `wire stock red: 3 entities, 5 wires; on poles: spk/m0 to note/m0 34.0
  tiles over 3 poles (3 added)`.
- The added poles join the power network too (the codec's copper wires).
- `wire-too-far` stays for when no chain exists.

## The rate model

A raw condition is taken as always open, as a `when` with no `cycle` is. LANGUAGE.md says so.

## Checked on a laptop server

`python tools/laptop_server.py circuits` (`LaptopServer("circuits")`, fk-play, Factorio 2.0.77,
2026-10-31). The design is in the script (`ALERT_FK`): a storage chest, an `Alarm` and a
`Display`, written only with the prelude's kinds and `cb.`/`bp.` fields. The panel stands 34 tiles
from the speaker.

- `fk lab` built it: 7 entities, the diff ok 7.
- The red wires read back from the game, west to east: chest to speaker, speaker to three medium
  poles, the last pole to the panel.
- The chest stocked by script, 2 s each:

  | plates | the speaker sees | its condition holds | the panel sees | the panel shows |
  |---|---|---|---|---|
  | 100 | 100 | false | 100 | Iron plates OK |
  | 20 | 20 | true | 20 | Iron plates low |
  | 100 | 100 | false | 100 | Iron plates OK |

  "Holds" is the game's own `fulfilled` flag on the speaker's condition: while it holds, the
  speaker sounds and shows its alert. A headless server has no player to receive the alert, so
  the flag is what can be read.
- Drift: no hand edit after the build. After the speaker's volume and the panel's `always_show`
  were changed by script, the diff named both: `bp.parameters={"playback_mode":"global",
  "playback_volume":0.5} (the paste sets ... "playback_volume":1)`.

Measured on the way (same server): the blueprint fields of a set-up speaker, display panel,
roboport and lamp, and their defaults. A display panel's shown message is `display_panel_text`;
its messages are `control_behavior.parameters`. A train stop's name is `station`.

## Checks

- Golden: 54 of 54 identical against 2.0.78.
- `tests/test_open_circuits.py`: the value syntax and its errors, raw settings on a set line, an
  instance, a kind and a hand, the game's forms, the codec and the `.fkp` round trips, a cb. over
  a typed setting, every refusal, the prelude's presets, signals from the game, any building on a
  wire, and drift.
- `tests/test_circuits.py`: a long wire hops along poles it adds, uses the poles that stand,
  passes a pole on another net of its colour, and is `wire-too-far` with no room for a pole.
- Full suite: 1341 tests OK.

## Not in this release

- A `when` on a speaker or a display panel: write `cb.circuit_condition`. `when` enables the
  entity types it did before.
- A radar link for very long runs.
- Deep merge: a kind's object field is replaced whole by the instance's.
