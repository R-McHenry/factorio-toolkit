# Toolkit 2.0.71: selector combinators in a Literal, and the circuit auto mall

Rory, 2026-10-30: "try and design an auto mall that uses combinators and one assembler and one
requester chest and an output chest". The mall is in `factorio-design\drafts\automall-20261030`
and runs on the lab at 2200,400.

## The catalog

A Literal refused it: "prototypes the catalog lacks: infinity-chest, selector-combinator". Both
are in the catalog now, next to the other combinators: the selector is 1x2 and needs power, and
the infinity chest (the lab's, for feeders) is 1x1.

## LANGUAGE.md

"Combinators the language doesn't write yet: a Literal" says how a combinator circuit goes into a
design today, and lists three things the game does that a hand-written blueprint can get wrong:
- an assembler keeps no network selection;
- a requester's requests from the circuit need `circuit_mode_of_operation: 1`;
- a decider outputs `each` only when a condition reads `each`.

The factorio processor's station file had the first two the other way, which is what the mall's
first two lab builds hit.

## Tests

`test_literal`: the two prototypes import in a Literal.
