# 2.0.4

- `fill=N` (A7): every inserter that feeds the machine now takes the same `if=ITEM<N` condition on
  the same red wire as the inserter that takes its product into the chest, so the machine is held
  too and finishes at most the craft in progress. A machine with no input inserter to gate (fed by
  a belt or the ground) gets a `LIMIT` line: it keeps crafting past N, and `keep=` may suit better.
