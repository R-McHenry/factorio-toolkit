# Toolkit 2.0.52: two voices for the checks

Rory, 2026-10-27: "search through their toolkit for loud warnings like MISSING and try and come up
with more comfortable replacements that are neutral and descriptive and less loud and frantic.
MISSING can probably become not-placed." And: "some warnings like CLOG should stay loud." Then:
"what is LANES? That might be detecting spillage which could be SPILL."

So the labels come in two voices now, and the capitals mean something:

- **loud, in capitals**: something will stop working - a belt fills, machines starve, a build never
  happens. Eight labels keep their shout: `CLOG`, `SHARED_SINK`, `SUSHI_SINK`, `SUSHI_LIMIT`,
  `SPILL` (was `LEAK`), `WRONG-LANE` (was `LANE`), `NO_POWER`, `UNREACHED`.
- **descriptive, lowercase**: what is missing, what stands elsewhere, what happened. The usual
  answer is the next build, so nothing shouts: `not-placed` (was `MISSING`), `no-position`,
  `not-where-designed`, `other-entity`, `other-item`, `unowned`, `settings-changed`, `no-feed`,
  `short-feed`, `no-taker`, `no-destination`, `no-route`, `partly-connected`, `cannot-carry`,
  `two-nets`, `feed-rides-on`, `could-pair`, `no-limit`, `no-rate`, `too-thin`, `size`,
  `does-not-fit`, `re-laid`, `taken-up`, `by-hand`, `malformed`, `needs-research`, `short-stock`,
  and the rest of the table in [CHECK-VOICE.md](CHECK-VOICE.md).

Two names were doing damage by being confusable: `LANES` and `LANE` sat one letter apart with
opposite meanings. `LANES` says "these two belts are half empty, one belt would carry both" - it is
advice, in the `ADVICE` family, and it is now `could-pair`. `LANE` says "items are on a belt lane
that isn't theirs" - a fault, and it is now `WRONG-LANE`, in the loud list. `LEAK`, the spillage
check, is `SPILL`: the same alarm in a plainer word.

## What changed underneath

- `fkcore`: ~90 emitted labels renamed. Python was edited token by token (`tokenize`), so only
  string text moved: no identifier, no docstring delimiter, no f-string expression.
- `Check.__str__` no longer pads the code into a column: the codes now run from `ok` to
  `not-where-designed`, and a padded column of them was exactly the loud, mechanical look this
  release is about. A line reads `no-feed steam b1: ...`, one word then its subject.
- `stop_on` folds case and knows the old words (`_OLD_STOPS`: `invariant` -> `malformed`,
  `UNROUTED` -> `no-route`, `NO_SINK` -> `no-destination`, ...), so a pinned run's build script, or
  one an upgrade has not rewritten yet, still stops on the same things it did before. The default
  stop stays `malformed`, so malformed data still cannot be written.
- `upgrade_run`: `_stops` compares the new words and maps the old ones, so an upgrade adds only the
  stops a run really lacks; its inserted `size` and `hands` lines keep their columns.
- `TOOLKIT.md`'s "The checks" is regrouped into the two voices: the eight loud ones first, then the
  thirty that describe a state.
- `tests/data/elaboration-baseline.json` is regenerated (32 of 42 designs move: the digest covers
  the check lines).

## What did not change

- The messages themselves: what each line tells you, and what to do about it, is word for word the
  old text. Only the label in front of it moved.
- `fk look`'s per-tile markers (`EMPTY`, `FULL`, `DAMAGED`, `FLUID_DRY`, `WRONG_TYPE`, ...): they
  are one cell of an ASCII grid and keep their terse spelling. `fk look`'s `GHOST SHORT` /
  `GHOST LOCKED` do follow the checks (`ghost short`, `ghost needs-research`).
- The rules: FAIR-PLAY.md is untouched.

## Verified

- The full suite: **1006 tests, OK**.
- The loud family is unchanged in substance: `0 SPILL` in the routed report, `CLOG` still stops
  nothing and says everything, and a build with malformed data still stops on it.
- A run pinned to 2.0.51 keeps the old words until it is upgraded: a run's toolkit is its own
  commit. Upgrading it is `kickoff/upgrade_run.py`, and it reads the old `stop_on` words.

## For the player

If you are reading this in a run that was just upgraded: the checks you know changed their names,
nothing else about them did. `MISSING` is `not-placed`, `LEAK` is `SPILL`, `LANES` is `could-pair`,
`UNFED` is `no-feed`. The capitals still mean "read me now".
