# Toolkit 2.0.1 (2026-10-22): what the first lead run's base needed said before it was built

Point fixes after 2.0 from the first lead run's FRICTION.md and RETRO.md (run 20261021-2039).
No new rules: checks warn, never gate.

## `UNDERFED`: a net whose drivers make less than its consumers take

Copper was the short plate all run, 40 a minute from 4 drills against the 75 or so red and green
asked, and nothing in the design said so: the lead found it from the game's stats. `report_rates`
now says it on paper: a net whose drivers, at what everything else lets them run, make less than
its consumers would take (by more than 5%) is an `UNDERFED` line with both rates, how fast the
consumers run for it, and the `fk plan ITEM RATE` that sizes its drivers. Only where a shortage
starts: a net whose drivers an input of theirs holds back is left to that input's line, so a
short ore patch is one line, not one per step down the chain. It is advice (`ADVICE`), like
`CLOG` and `UNLIMITED`. (`fkcore.rates.underfed`, tests in test_rates.)

## `UNREACHED`: what no powered roboport reaches, before the paste

The plates worker's coal site was powered by a bridge through ground no powered roboport
reached, and the relay roboport that would have reached it was powered only through that bridge:
its poles stood as ghosts for ever. The world line says so for ghosts that stand; the build's
`diff` step now says it before the paste: the entities the paste lays where no powered
roboport's construction area reaches (a roboport whose cell transmits), counting the roboports
the paste lays where robots reach as reaching too, and the power-bridge poles among them by
name. Checked on a laptop test server (2.0.77).

## `cover power` keeps the built poles of another kind

Medium poles were SHORT before steel, and switching the cover to small poles dropped every
medium pole, the built ones too, so the whole base would have been re-laid; the labs/coal worker
took six tries to place small poles by hand. The `diff` now records which poles stand built
(`out\standing.json`, pulled back with the rest), and the next build's `cover power` keeps a
pinned pole of another kind (same footprint) when it stands, laying the new kind only where the
old one never stood. Without that record, as before.

684 + 4 tests: 688 OK.
