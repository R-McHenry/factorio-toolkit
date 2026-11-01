# Toolkit 2.1.17: the documents

PLAN-2.1, phase 16. The player docs say 2.1 as it stands, as one text rather than release by
release. No code changes; `__version__` is 2.1.17.

- **LANGUAGE.md** opens with "The library": `Machine` and `Entity`, `kind`, the prelude (a run's
  over the toolkit's), `tiers` and `machine=auto`, cells with parameters, and a table of the
  template's `cells.fk`. Rows follow as the older way. The sections the 2.1 releases added
  (ribbons, buffers and sushi gates, fluid ports, cells within cells, open circuits, combinators,
  power domains) are tidied into one text, and release numbers that only dated a feature are gone.
- **TOOLKIT.md**: "What `fk look` says" covers `--zoom`, `--layers` and `--image`; a new section,
  "The run's history", covers the samples, `fk stats --history`, `--page` and `--sample`; the
  checks gain `copper`, `gate-auto` and `limited`; a new "Advice: `fk check`" lists
  `limited-why`, `row-cell` and `gate-auto`, and says what a refusal is (`no-fluidbox`). A stray
  half line before "When you need something" is gone.
- **EXAMPLES.md** leads with five examples that build: `plastic-cell.fk` (a cell around a
  `Machine`, gas through the Stack on a pipe), `library-lines.fk` (SmelterPairs into cable cells),
  `ribbon-bus.fk` (four smelter columns, four belts as a ribbon), `power-shed.fk` (a lab field
  behind a switch, the library's `Hysteresis`) and `mall-loop.fk` (the library's sushi mall). The
  older examples follow, unchanged.
- **`agent/docs/examples/cells.fk`** is a copy of the kickoff template's, so the examples build
  where they stand; `tests/test_examples_21.py` keeps the two equal and builds the five on paper.
- **`docs/RELEASE-2.1.md`**: the 2.1 line on one page.
- The kickoff template's `game\prelude.fk` is `fkcore\prelude.fk`, byte for byte.

## Checked against the code

Each command and flag in the docs was checked against `agent/fk.py` and `fkcore`. Where a release
note and the code differ, the docs follow the code:

- A map look (counts per cell, no verdicts) is zoom 8 and up, or zoom 2 or 4 over more than
  65536 tiles. 2.1.2's notes and TOOLKIT.md said any area over 65536 tiles; a zoom 1 look always
  reads every entity (`vision.map_mode`).
- `fk look --design` takes `--zoom`, `--layers` and `--image` too.

## Checks

- Golden: the 54 designs of 2.1.12's snapshot identical; the six new example files are new to the
  corpus.
- Full suite: 1520 tests, OK (390 s).
