# Toolkit 2.0.27: properties on objects (`set`), with keep= and fill= as its shorthands

Rory, 2026-10-25: "We need a system that lets the designer control properties of objects. So in this
case its an output inserter. The language should have a way to identify the output inserter and
specify parameters of it like circuit conditions." … "fill=N should be implementable kind of like
keep=n but also with a wire to that inserter put in somewhere as well, that one is the real gold
standard for production limiting."

## The statement

```
set belt.out            : logistic=transport-belt<200   # the hands that take belts out
set ins.out -> ibox     : if=inserter<50                # only the hand whose sink is ibox
set ins                 : logistic=inserter<50          # the machine itself: stops the craft
set pipe.out            : logistic=pipe<100             # a row: all its output hands
```

- **Selectors**: `NAME` (its machines), `NAME.out` (the hands that take its product out — its own
  output hands, and the hands further down a net it drives), `NAME.in` (the hands that feed it),
  and `-> NAME` to keep only the hands whose sink is that instance. The arrow is the case that
  started this: a maker feeding a chest *and* a consumer row has two output hands, and only the
  chest hand should carry the chest's limit.
- **Properties**: `if`, `logistic`, `filter`, `read`, `signal`, `signals` — the codec's circuit
  attributes, no new vocabulary.
- **Truthful**: every `set` reports the hands it hit (`on 2 hands (~out/i0, ~out/i1)`); a selector
  that matches nothing, an `if=` with no chest to read, or an unknown property is a `SELECT` check
  line. Silence was `fill=`'s worst old failure.

## `keep=` and `fill=` are the shorthands, lowered to those lines

They keep working, and they are no longer heuristics: each one expands to the `set` statements it
always meant, so its report line names the object it touched.

- `keep=N` → `set NAME.out: logistic=ITEM<N` — the logistic network's count, no wire; the maker
  still crafts into its output buffer.
- `fill=N` → `set NAME.out -> CHEST: if=ITEM<N` **and** `set NAME.in: if=ITEM<N`, both on the
  chest's red wire. The chest's own count holds the hand that fills it **and** every hand feeding
  the machine, so the machine stops at most one craft past N. No robots, and the tightest limit:
  the gold standard Rory named.
- `fill=` with no chest to count is a `LIMIT` line now (it used to do nothing, silently, when the
  product left on a belt).

## Migrating old mall code

| was | the same thing, written out |
|---|---|
| `belt = Assembler<recipe=transport-belt, keep=200>` | `set belt.out: logistic=transport-belt<200` |
| `ins = Assembler<recipe=inserter, keep=1000>` feeding a chest **and** a row | `set ins.out -> ibox: logistic=inserter<1000` (name the chest: a shared belt must not carry the row's condition) |
| `x = Assembler<..., fill=50>` straight into a chest | `set x.out -> ibox: if=inserter<50` and `set x.in: if=inserter<50` |
| `pipe = AsmRow<n=2, recipe=pipe, keep=100>` | `set pipe.out: logistic=pipe<100` |
| `Chest<provider, limit=8>` | unchanged: the chest's **bar**, 8 *slots* — storage, not a circuit |

Rule of thumb: the condition lives on the hand that has the job; `-> NAME` names that hand, and the
machine's own `logistic=` is the way to stop the craft.

## What changed in the code

- `lang.py`: the `set` statement (`Props`), parsed with its selector and its comma-separated
  properties.
- `elaborate.py`: the statements reach the factories with the other circuit source.
- `circuits.py`: `lay` has `setprops()` in place of `limits()`; `resolve` lowers `keep=`/`fill=` to
  `Props` (fill finds the chest its product goes into); `PROP_ATTRS` is the property vocabulary.
- `compact-mall.fk` migrated to one `set` per maker; `LANGUAGE.md` has "Properties on objects", the
  two shorthands with when to write `set` instead, and the migration table; `EXAMPLES.md`,
  `STRATEGY.md` and `TOOLKIT.md` follow.

## Tests (866, all green)

`tests/test_circuits.py` (`SetPropsTest`): a property lands on the named hand; `-> CHEST` takes only
that hand and reads its wire; a bare instance sets the machine's enable; a selector that matches
nothing is a `SELECT`; an `if=` with no chest is a `SELECT`; a changed property re-lays and a removed
one clears; `keep=` lowers to the hand's logistic condition; `fill=` lowers to the chest hand plus
the machine's input hands on the chest's wire; an unknown property is a `SELECT`; a set limit does
not quiet `CLOG` (only `limited` does).
