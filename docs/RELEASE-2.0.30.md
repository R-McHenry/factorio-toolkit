# Toolkit 2.0.30: ports reconcile with V1's `Belt[A | B]`

Rory, 2026-10-25: "for the A | B pair, check if that is duplicated or can be reconciled with the
`Belt[A | B]` port syntax."

## What the check found

**`Belt[A | B]` is the V1-era typed port, not v5.** `factorio-design\LANGUAGE.md` ("fk v3 — the base
as source", 2026-10-15) types a port's carrier: `in fuel: Belt[coal]`, `out plates: Belt[iron-plate]`,
`Belt[iron-plate]` = "one item, both lanes", `Belt[iron-ore | coal]` = "lane-split (south | north in
the local frame)", plus `Pipe[water]`, `Power`, `Robots`, `Wire.red/green`. `base\*.fk` is written that
way. v5 has no `Belt` or `Pipe` port type and no `Belt` template: the carrier is inferred from the item
(a fluid is a pipe), so `Belt[coal]` would add a word the item already decides.

**V2 removed the spelling on purpose.** `CORE-V1.md` lists it among the causes of the rewrite: "Lanes
leaked into ports and item types (`Belt[a|b]`, `side=`)" (cause 4); its glossary maps the old port
("tile + direction (+ lane)") to "**endpoint** = (machine, item, in/out), logical; **attach point** =
… geometric", and `lane` to "none in V1; 1.1 adds lanes only on lane-pair belts". `Belt[a|b]` and
`side=` are in the "what goes" list.

**So the pair is not a duplicate — it is the same idea one generation later.** The lane belongs to the
port's identity again, but with a real lane model behind it (`fkcore.lanes`, measured physics) and a
record (`.fkp`), where V1 had neither and invented `LANE_COLLISION` to catch the fallout. The lane
*pairing of nets* stays where V2 put it: the `lanes A | B` statement.

**The one meaning V1 had and the lane model could not write:** `Belt[iron-plate]`, one item on both
lanes. 2.0.29 refused `iron-plate | iron-plate`; that refusal was the toolkit's invention, not a
decision.

## The reconciliation, as shipped

One rule: **a port names what it carries; the item decides belt or pipe; the anchor names the tile and
the lane; `|` is the two lanes of one belt end, left then right.**

- **`item | item` is both lanes** (Rory, 2026-10-25). `Belt[X]` → `X | X`, `Belt[X | Y]` → `X | Y`: an
  exact mapping. The netlist still sees one item; the declaration is what says "both lanes".
- **A fluid is never a pair and never a lane**: `port w : in water | steam @s` and `port w : in water
  @sL` are refused, "pipes have no lanes", exactly as `lanes` refuses a fluid. A one-lane fluid port
  is a pipe, unchanged.
- **V1's order does not come back**: south | north was frame-bound; `lanes` is left | right looking
  downstream, and the pair uses that.
- **The `|` glyph has three uses** — the lane pair (`lanes`, ports) and a param-list separator
  (`Bus<… tap=w10|w25|w40>`, the only list use in the corpus). Phase 2's connection list replaces
  `load=`/`tap=`, after which `|` means exactly one thing. Nothing changed there.

## Tests (32 in `tests/test_ports.py`)

New: `Belt[iron-plate]` as `iron-plate | iron-plate` (two lanes, one item, no check lines); a pair of
fluids refused; a lane pinned on a fluid refused. The 29 from 2.0.29 still pass, and the elaboration
baseline over the 42 existing designs is unchanged.

## Still open

Whether a bare ref or `gears.*` on a sealed module should mean its ports rather than being refused
(§10.4 of the plan).
