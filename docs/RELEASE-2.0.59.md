# Toolkit 2.0.59: n=auto on a Stack, sized on the rate model

Rory, 2026-10-29: "Ideally it should have the rate model, and just optimise the params to get the
desired rate."

## A Stack's count is a parameter

`Stack<cell=FurnaceCell, n=auto>` (or `n=auto 2..12`) leaves the number of cells to the build's
`size` step. It is an outer search around the row sizing (`size.size`, the rows now
`size._size_rows`):

1. **Start** each auto Stack at its low bound (or a count given to the step).
2. **Evaluate** a set of Stack counts: elaborate at them, size the auto rows as before, run the
   rate model, and measure every want: the surface's targets, the factory's asserts, and what each
   net from the Stack asks for its consumers.
3. **Grow**: while a want fails, try one more cell on each auto Stack and keep the one that cuts
   the shortfall most. Stop when no cell helps, or a Stack is at its top.
4. **Trim**: each Stack gives back cells while every want that holds still holds; the want that
   breaks at one fewer is what its count serves (`out\size.txt`).

A cell can be any machines (a circuit cell has cable and circuit assemblers), so the count is never
guessed from a recipe. Each step is the model's answer at that count. Every count tried is solved
once and kept.

## Measured on paper

| design | sized to |
|---|---|
| a FurnaceCell line into one gear assembler-2 (3 plates/s asked) | 5 cells (3.125/s) |
| the same into a chest, `assert col.rate >= 2/s` | 4 cells (2.5/s; 3 make 1.875) |
| a copper FurnaceCell line into a CircuitCell line, `assert col.rate >= 3/s` | 8 and 2 cells, 3.33 circuits/s |

The circuit case shows the model judging, not a recipe ratio. One circuit cell has four circuit
assemblers, enough for 3/s on paper, but its six cable assemblers then share 5 copper plates/s and
the model gives 2.67 circuits/s, so it takes two.

## Smaller changes

- A feed want on a net that a port drives (a Stack's last cell) is measured by what the net
  delivers. A port passes items on, so the net's "can make" read 0.
- `n=auto` on anything else still says it is the count of a row or a Stack.

## Not changed / found on the way

- A build records no Stack count in its layout, so the next build starts the search again from the
  low bound and reaches the same count (a few more model solves).
- A rebuild of a Stack line re-lays some of its routes even with nothing changed: 8 of 21 on a
  5-cell furnace line, the same with `n=5` written. That predates this release.

## Tests

`tests/test_stack_auto.py` (6): elaborated at the low bound or the step's count, sized to a
consumer's ask, to an assert, at its top with a size line, two Stacks together, and a single machine
refused.
