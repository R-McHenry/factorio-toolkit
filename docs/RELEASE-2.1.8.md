# Toolkit 2.1.8: buffers, limited "...", and names inside a Literal

The buffers phase of `assessment-20261031\PLAN-2.1.md` (phase 7 of "Order"), sections G and H.

## Buffers

- A buffer is a role. One net fills it and another drains it.
- `b = Buffer` is a steel chest. It is a kind in the prelude,
  `kind Buffer = Chest<plain, hold, chest=steel-chest>`. `Buffer<chest=iron-chest, bar=20, item=iron-plate>` sets the
  chest, the slots it may fill, and what it holds when no net says. Its items are what the nets
  into it carry.
- `module NAME buffer { ... }` makes a module's ports the buffer's ends. With parameters
  (2.1.7) and a frame it is `module NAME<p> buffer size WxH`; `buffer` may also come after the
  size. Its inside is the designer's. A buffer module with no ports is refused.
- The rate model treats a buffer as an unlimited supply downstream and an unlimited sink upstream.
  `fk rates` ends with one line per buffer and item:
  `BUFFER b: +60.0/min iron-ore (filling: in 60.0, out 0.0)`, or `draining`, or `steady`.
- A buffer an unbounded source feeds fills without end on paper (`+unbounded/min`). When that
  net is gated (`when`), the gate tops up what goes out, and the line is steady.
- A buffer gets no `no-taker` and no `no-rate`. A buffer whose nets are all `limited` gets no
  `SUSHI_LIMIT`. A sushi net with a buffer on it gets no `SUSHI_SINK`, since what no machine
  takes ends in the buffer or goes round by it. `CLOG` stays.
- The routed rates (`out\report_rates.txt`) treat a buffer the same way: a sink on the nets into
  it and an unlimited supply on the nets out of it.
- The old failure "driver gbuf makes no electronic-circuit" is gone: a buffer makes what the nets
  into it carry.

`hold` is the chest flag that makes the role (`templates._hold_chest`); the prelude's `Buffer`
names it with a steel chest. A run's own `game/prelude.fk`, or a kind of the same name in a file,
can make it another chest. A `module X buffer` is a module flag. The template's
`game/prelude.fk` has the line too; a run made before 2.1.8 keeps its own prelude, so add the line
there to use `Buffer`.

## `limited "..."`

- `net NAME limited "what limits it": ...` says how the design limits what each maker puts on
  the net. `fk explain FILE NET` and `fk check` show the string.
- A bare `limited` still works. `fk check` asks for the string on a sushi net, as an
  `advice limited-why` line. Advice lines are only in `fk check`, so the rates and the build
  reports are unchanged.
- An empty string is refused: write a bare `limited`.
- `CLOG` stays the one warning on a sushi net, and only `limited` clears it.
- `fk explain FILE NET` is new: one net's items, drivers, consumers, lanes, buffers and limit.

## `read=hold-all`

- A belt's `read=hold-all` reads the whole belt, not one tile (the game's "entire belt" mode).
- `set NET: read=hold-all` puts it on the belt a wire reads on that net.

## Names inside a Literal

- A JSON Literal file may hold `"names": {"asm10": 37}`, a name to an entity's index in the
  file (from 0).
- `automall.asm10` is then a net end. The router reaches it from outside the Literal.
- `fk explain` lists the names. `fk capture` writes them: `asm1`, `furnace1`, `drill1`, ... in
  file order.
- A name with a dash, an index out of range, or an entity outside the box is refused. So is a net
  end that names an entity that is no machine.
- A blueprint Literal now keeps its circuit settings (`if=`, `read=`, ...). Before, the codec read
  them back typed and the Literal dropped them; only `config` and the wires came through.

## Measured in the lab

`python tools/lab_buffers.py [line|one|loop|all]`, on a laptop server ("buffers", scenario
fk-play):

- A drill line into a buffer: filling at +78/min against the model's +60/min. The lab force has
  +30% mining productivity, so +78 is what the model says with it.
- The same line drained by three electric furnaces: -34/min against the model's -52.5/min, or
  -34.5 with the productivity. The furnaces made 112.4 plates/min against 112.5.
- One assembler (electric mining drills) with a chest end buffer and three gated sources: 15.0
  drills/min, as the model says. The buffer held each item at its gate for ten game minutes.
- Four assemblers on a sushi loop (gears, cable, belts, pipe on AM1s), an end buffer feeding the
  head, and three bulk-inserter sources gated on what the loop holds (the belt read `hold-all`
  plus the end buffer), an hour of game time. The model says 60, 120, 120 and 60/min; the game
  made 59.8, 109.5, 113.6 and 59.8/min (100%, 91%, 95%, 100%). Every machine crafted in every
  two-minute window, and the loop never held more than its gate plus one bulk hand (iron 76..95
  for 80, copper 37..59 for 40, gears 36..53 for 40), so the belt never stopped. The loop is a
  Literal whose file names its assemblers, and the products leave on routes the router laid to
  `loop.asm1` ... `loop.asm4`.
- With gates of 60/20/20 the cable and belt machines made 83% and 76%: a tight gate leaves too
  few items going round. A fast inserter as the iron source brought about 2/s, half the 4/s the
  machines take.

## Advice for a sushi loop

- Gate each source well above what one lap needs. With gates of 80 iron, 40 copper and 40 gears
  and bulk-inserter sources, the four machines ran at 91 to 100% of the model. With 60/20/20 the
  cable and belt machines dropped to 83% and 76%: too few items go round, and a machine waits for
  one to come by.
- A source must bring what the machines take. A fast inserter loads about 2/s onto a belt; the
  loop's machines took 4 iron/s, so its iron source is a bulk inserter.
- The loop holds its gate plus about one hand of each source, since an enabled inserter finishes
  its swing.

## Tests

`tests/test_buffers.py`: the grammar and its refusals, the chest and module buffers, the rate
lines, `limited "..."` and its advice, `read=hold-all`, and Literal names and circuit settings.
